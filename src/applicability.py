"""Supported is not applicable: verifying a cited recommendation against the user's decision context.

Verifiers over one local model (config/verifier.json):

  rules            qualifier lexicon: a printed condition the user's words contradict -> flag
  judge            LLM judge: is the recommendation correct for this user (source + situation + answer, one call)
  judge_checklist  the same judge, given the condition types to check and told to intervene only when the decision changes
  dcv              decision-conditioned verification: the model reads every printed variant and the user's situation into
                   fixed slots; code selects the applicable variant, recomputes and flips only when the decision changes
  direct           answers the question from the excerpt, ignoring the assistant's answer
  qbr              quote-bound recalculation: the checklist judge also lists operands with verbatim quotes and an expression;
                   code binds each operand to a printed clause and its condition and, if every check passes, certifies the
                   decision by evaluating the expression (policies: bound_first, judge_only, agree, source_bound)

assist() is the assistant call used for the natural-answer studies.

Every verifier returns {"verdict": correct|incorrect|insufficient, "corrected": str, "calls": [...]}.
"""
from __future__ import annotations

import ast
import json
import re
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / "config" / "verifier.json").read_text(encoding="utf-8"))
SEED = 20261115


def _call(messages, schema, max_tokens=1400):
    body = {"model": CFG["alias"], "messages": messages, "temperature": 0, "seed": SEED, "max_tokens": max_tokens,
            "response_format": {"type": "json_schema", "json_schema": {"name": "out", "strict": True, "schema": schema}}}
    if CFG.get("chat_template_kwargs"):
        body["chat_template_kwargs"] = CFG["chat_template_kwargs"]
    req = urllib.request.Request(CFG["endpoint"].rstrip("/") + "/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    started = time.perf_counter()
    raw = json.loads(urllib.request.urlopen(req, timeout=600).read())
    record = {"messages": messages, "response": raw, "seconds": round(time.perf_counter() - started, 2)}
    text = raw["choices"][0]["message"]["content"]
    try:
        return json.loads(text), record
    except ValueError:
        return None, record


def _obj(props, required=None):
    return {"type": "object", "properties": props, "required": required or list(props), "additionalProperties": False}


def _enum(*values):
    return {"type": "string", "enum": list(values)}


NUM_OR_NULL = {"type": ["number", "null"]}


# ---------------------------------------------------------------- holistic judges (baselines)
JUDGE_SCHEMA = _obj({  # reasoning first, so the verdict fields follow it
    "reason": {"type": "string"},
    "claim_supported_by_source": _enum("yes", "no"),
    "claim_applies_to_user": _enum("yes", "no", "insufficient"),
    "recommendation_correct_for_user": _enum("yes", "no", "insufficient"),
    "corrected_recommendation": {"type": "string"},
})

JUDGE_SYSTEM = ("You check an AI assistant's recommendation for one specific user. You are given a source excerpt, "
                "the user's situation, and the assistant's answer, which quotes the source. Decide whether the "
                "recommendation is correct for THIS user. Answer 'insufficient' when the source does not establish "
                "the answer for this user.")

CHECKLIST = ("Before deciding, check every printed condition attached to the quoted number against the user's situation: "
             "annual vs monthly billing; introductory (first-term) price vs renewal price and how long the user will pay; "
             "price per user/seat/item vs total for the user's count; prices excluding vs including tax and whether the user "
             "pays tax on top; GAAP vs non-GAAP figures; quarter vs year-to-date period; relative vs absolute effect size; "
             "and whether the user belongs to the population or subgroup the evidence studied. If a condition does not "
             "match, find the value printed for the user's condition, recompute the user's number, and compare it with the "
             "user's limit. Mark the recommendation wrong ONLY if the decision changes; a mismatch that leaves the decision "
             "unchanged is still correct.")


def _judge_messages(item, case, checklist):
    system = JUDGE_SYSTEM + (" " + CHECKLIST if checklist else "")
    user = (f"SOURCE EXCERPT ({item['source'][0]}):\n{item['excerpt']}\n\nUSER'S SITUATION:\n{case['context']}\n\n"
            f"ASSISTANT'S ANSWER:\n{case['answer']}")
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def judge(item, case, checklist=False):
    out, rec = _call(_judge_messages(item, case, checklist), JUDGE_SCHEMA, max_tokens=2000)
    if out is None:
        return {"verdict": "error", "corrected": "", "calls": [rec]}
    verdict = {"yes": "correct", "no": "incorrect", "insufficient": "insufficient"}[out["recommendation_correct_for_user"]]
    return {"verdict": verdict, "corrected": out["corrected_recommendation"], "raw": out, "calls": [rec]}


# ---------------------------------------------------------------- qualifier rules (baseline)
RULES = [  # (printed qualifier in the quote, user wording that contradicts it)
    (r"(?i)billed annually|paid annually|billed yearly|when paying annually", r"(?i)month to month|monthly, with no annual"),
    (r"(?i)for the first (\d+ )?months?|first year", r"(?i)\b(two|three|four|\d+) (years|months)\b|keep it for"),
    (r"(?i)per user|per seat|/user|per member", r"(?i)team of ([2-9]|\d\d)"),
    (r"(?i)excl\. VAT|excluding VAT", r"(?i)VAT on top|private customer"),
    (r"(?i)non-GAAP", r"(?i)uses GAAP figures"),
    (r"(?i)third quarter|three months", r"(?i)nine.months|year.to.date"),
    (r"(?i)relative risk reduction|\bRRR\b", r"(?i)absolute terms|percentage points"),
    (r"(?i)≤ ?\d+ years|overweight|obese|pediatric|children|metabolic syndrome", r"(?i)\d+ years old|BMI|adult|do not have"),
]


def rules(item, case):
    quote = case.get("quote") or item["quote"]
    for printed, contradicts in RULES:
        if re.search(printed, quote) and re.search(contradicts, case["context"]):
            return {"verdict": "incorrect", "corrected": f"printed condition /{printed}/ contradicts the user's situation", "calls": []}
    return {"verdict": "correct", "corrected": "", "calls": []}


# ---------------------------------------------------------------- decision-conditioned verification (ours)
SLOTS = {
    "billing_term": ("annual", "monthly", "not stated"),
    "term_position": ("introductory", "renewal", "not stated"),
    "charge_basis": ("per user or seat", "per item", "flat total", "not stated"),
    "tax": ("excluding tax", "including tax", "not stated"),
    "accounting": ("GAAP", "non-GAAP", "not stated"),
    "period": ("quarter", "year to date (e.g. first nine months)", "full year", "not stated"),
    "effect_scale": ("relative (percent of baseline risk)", "absolute (percentage points)", "not stated"),
}

READ_SOURCE_SCHEMA = _obj({
    "variants": {"type": "array", "items": _obj({
        "quantity": {"type": "string"},
        "same_quantity_as_claim": {"type": "boolean"},
        "value": {"type": "number"},
        "quote": {"type": "string"},
        **{k: _enum(*v) for k, v in SLOTS.items()},
        "term_months": NUM_OR_NULL,
        "population": {"type": "string"},
    })},
    "claim_variant": {"type": "integer"},
})

READ_SOURCE_SYSTEM = ("You read a source excerpt. List the values printed in the excerpt for the same quantity as the claim "
                      "(same product or plan price, same company metric, same treatment effect), including the claim's own value "
                      "and the values printed for other conditions (other billing terms, renewal prices, GAAP and non-GAAP, other "
                      "periods, relative and absolute effects). Copy each value exactly as printed (a loss in parentheses is "
                      "negative; 1.13 billion is 1130 if the claim is in millions). For each value record the conditions printed "
                      "with it; use 'not stated' when the excerpt does not say. term_months is the length of time the price covers "
                      "(12 for 'every 12 months' or 'billed annually' prices quoted per year; 1 for monthly), else null. population "
                      "is the group of people a study or trial measured that value in; leave it empty for prices and company figures. claim_variant is the index of the claim's value. quantity names what each value measures (e.g. 'operating margin', 'Starter plan price'); "
                      "The SAME quantity under a different condition (GAAP vs non-GAAP, another period, billing term or price term, relative vs absolute "
                      "effect of the same treatment on the same outcome) IS the same quantity: list it with same_quantity_as_claim true. Do not list "
                      "values of other metrics, plans or outcomes. List at most 8 values. Take each condition from the words printed with that value: "
                      "'third quarter' or 'three months' = quarter; 'first nine months' or 'nine months ended' = year to date; use 'not stated' for "
                      "slots that do not apply to this kind of quantity.")

READ_USER_SCHEMA = _obj({
    **{f"wants_{k}": _enum(*v) for k, v in SLOTS.items() if k not in ("term_position", "charge_basis", "tax")},
    "keep_months": NUM_OR_NULL,
    "count": NUM_OR_NULL,
    "pays_tax_on_top_percent": NUM_OR_NULL,
    "limit": {"type": "number"},
    "limit_unit": {"type": "string"},
    "limit_direction": _enum("at most", "at least"),
    "in_population": _enum("yes", "no", "unclear", "not applicable"),
})

READ_USER_SYSTEM = ("You read a user's situation and fill fixed fields. Use 'not stated' or null when the user does not say. "
                    "keep_months: how long the user will keep paying, in months. count: number of users, seats or items the user "
                    "needs. pays_tax_on_top_percent: the tax rate the user pays on top of net prices (0 if they compare net prices "
                    "or reclaim tax). limit: the user's threshold number, with its unit exactly as the user wrote it (limit_unit) and its direction. wants_*: which basis the user's "
                    "threshold is stated in (e.g. 'month to month' = monthly; 'first-nine-months figures' = year to date; 'percentage points in "
                    "absolute terms' = absolute; 'GAAP figures' = GAAP). in_population: does the user belong to the population or subgroup named below? "
                    "('not applicable' if no population is named).")


def _verdict_word(answer):
    head = answer.split(".")[0].lower()
    return False if re.search(r"\bfails\b|does not fit|\bno\b", head) else True


def _choose(variants, claim, wants):
    """The printed variant whose conditions match what the user wants; conflicts disqualify."""
    best, best_score = None, -1
    for v in variants:
        score, conflict = 0, False
        for slot, wanted in wants.items():
            if wanted == "not stated":
                continue
            if v[slot] == wanted:
                score += 1
            elif v[slot] != "not stated":
                conflict = True
        if not conflict and (score > best_score or (score == best_score and v is claim)):
            best, best_score = v, score
    return best


def dcv(item, case, source_cache=None):
    calls = []
    key = item["id"]
    if source_cache is not None and key in source_cache:
        src = source_cache[key]
    else:
        msg = [{"role": "system", "content": READ_SOURCE_SYSTEM},
               {"role": "user", "content": f"SOURCE EXCERPT:\n{item['excerpt']}\n\nCLAIM:\n{item['claim']}"}]
        src, rec = _call(msg, READ_SOURCE_SCHEMA, max_tokens=3000)
        calls.append(rec)
        if source_cache is not None and src is not None:
            source_cache[key] = src
    if not src or not src["variants"]:
        return {"verdict": "error", "corrected": "source reading failed", "calls": calls}
    variants = src["variants"]
    claim = variants[min(max(src["claim_variant"], 0), len(variants) - 1)]
    populations = sorted({v["population"] for v in variants if v["population"].strip() and v["population"].strip().lower() != "not stated"})
    msg = [{"role": "system", "content": READ_USER_SYSTEM},
           {"role": "user", "content": f"USER'S SITUATION:\n{case['context']}\n\nPOPULATION NAMED BY THE EVIDENCE: "
                                       f"{claim['population'] if claim['population'].strip().lower() not in ('', 'not stated') else (populations[0] if populations else 'none')}"}]
    usr, rec = _call(msg, READ_USER_SCHEMA, max_tokens=500)
    calls.append(rec)
    if usr is None:
        return {"verdict": "error", "corrected": "user reading failed", "calls": calls}

    out = decide(src, usr, case["answer"])
    out["calls"] = calls
    return out


def decide(src, usr, answer, selection=True, arithmetic=True, counterfactual=True, abstention=True):
    """The deterministic half of DCV, from the two readings. The flags switch off one module each
    (ablations): selection = pick the printed variant matching the user's conditions; arithmetic = apply
    the user's count, tax and keep-time; counterfactual = recompute the decision and intervene only if it
    flips (off: flag every condition mismatch); abstention = say 'insufficient' when nothing applies."""
    claim = src["variants"][min(max(src["claim_variant"], 0), len(src["variants"]) - 1)]
    variants = [v for v in src["variants"] if v is claim or v.get("same_quantity_as_claim", True)]
    trace = {"source": src, "user": usr}
    if usr["in_population"] == "no":
        if abstention:
            return {"verdict": "insufficient", "corrected": "the evidence studied a different population than this user", "trace": trace}
        if not counterfactual:
            return {"verdict": "incorrect", "corrected": "population mismatch", "trace": trace}
    wants = {k: usr[f"wants_{k}"] for k in ("billing_term", "accounting", "period", "effect_scale")}
    unit = usr.get("limit_unit", "").lower()
    if wants["effect_scale"] == "not stated" and "percentage point" in unit:  # the unit itself names the scale
        wants["effect_scale"] = SLOTS["effect_scale"][1]
    chosen = _choose(variants, claim, wants) if selection else claim
    if chosen is None:
        if abstention:
            return {"verdict": "insufficient", "corrected": "no printed value matches the user's conditions", "trace": trace}
        chosen = claim

    value, adjusted = chosen["value"], False
    keep, term = usr["keep_months"], chosen["term_months"]
    if arithmetic and chosen["term_position"] == "introductory" and keep and term and keep > term:
        renewal = next((v for v in variants if v["term_position"] == "renewal"), None)
        if renewal is None:
            if abstention:
                return {"verdict": "insufficient", "corrected": "the renewal price is not printed", "trace": trace}
        else:
            rterm = renewal["term_months"] or term
            value = (value + renewal["value"] * (keep - term) / rterm) / (keep / term)  # average per introductory-length term
            adjusted = True
    if arithmetic and chosen["charge_basis"] in ("per user or seat", "per item") and usr["count"]:
        value *= usr["count"]
        adjusted = adjusted or usr["count"] != 1
    if arithmetic and chosen["tax"] == "excluding tax" and usr["pays_tax_on_top_percent"]:
        value *= 1 + usr["pays_tax_on_top_percent"] / 100
        adjusted = True
    trace.update(chosen=chosen, user_value=round(value, 4))
    if not counterfactual:  # a condition checker: any mismatch is an alarm
        mismatch = chosen is not claim or adjusted
        return {"verdict": "incorrect" if mismatch else "correct", "corrected": "condition mismatch" if mismatch else "", "trace": trace}
    ok = value <= usr["limit"] + 1e-9 if usr["limit_direction"] == "at most" else value >= usr["limit"] - 1e-9
    trace["decision"] = ok
    if ok == _verdict_word(answer):
        return {"verdict": "correct", "corrected": "", "trace": trace}
    return {"verdict": "incorrect", "corrected": f"recomputed value {value:,.4g} vs limit {usr['limit']:g} ({usr['limit_direction']}): decision flips",
            "trace": trace}


# ---------------------------------------------------------------- quote-bound recalculation (second-generation method)
QBR_SCHEMA = _obj({
    "reason": {"type": "string"},
    "quoted_value_applies_to_user": _enum("yes", "no, another printed value applies", "no printed value applies to this user"),
    "operands": {"type": "array", "items": _obj({
        "name": {"type": "string"},
        "value": {"type": "number"},
        "quote": {"type": "string"},
        "from": _enum("source", "user"),
        "condition_words": {"type": "string"},
        "user_condition_words": {"type": "string"},
    })},
    "user_value_expression": {"type": "string"},
    "limit_operand": {"type": "string"},
    "direction": _enum("at most", "at least"),
    "recommendation_for_this_user": _enum("correct", "wrong", "cannot tell from the source"),
})

QBR_INSTRUCTIONS = (" Then show your computation so it can be checked: list every number you use as an operand with a short "
                    "identifier name, its value, and a VERBATIM quote of the words it comes from, copied from the SOURCE EXCERPT or from "
                    "the USER'S SITUATION. The quote must be the shortest clause (at most about 25 words) that contains the number. "
                    "condition_words: the words printed right next to that number that state its condition (e.g. 'billed monthly', "
                    "'GAAP', 'first nine months', 'then $0.125 per GB'), copied verbatim from the quote, or '' if none. "
                    "user_condition_words: the words of the user's situation that this condition must match (e.g. 'month to month'), "
                    "copied verbatim, or '' if none. Write user_value_expression as arithmetic over operand names only (+ - * / parentheses, "
                    "max, min) giving the value that should be compared with the user's limit, name the limit operand, and give its "
                    "direction. quoted_value_applies_to_user: 'yes' if the assistant's quoted number holds under the user's "
                    "conditions; 'no, another printed value applies' if a different printed number (or the quoted number with the "
                    "user's arithmetic) is the right one, then use that in your computation; 'no printed value applies to this "
                    "user' only if nothing in the source covers this user (for example, the user is outside the population "
                    "studied). recommendation_for_this_user is your own verdict on the assistant's recommendation.")

NUM = re.compile(r"\(?-?\d[\d,]*(?:\.\d+)?%?\)?")
CLAUSE = re.compile(r"(?<=[a-z%\d)])\.\s+|;\s*|\s+\|\s+|,?\s+\band\b\s+|,?\s+\bor\b\s+|,?\s+(?=then\b)")


def _norm(text):
    return re.sub(r"\s+", " ", text.replace("’", "'").replace("\xa0", " ")).strip().lower()


def _numbers(quote):
    out = []
    for m in NUM.finditer(quote):
        t = m.group(0)
        neg = t.startswith("(") and t.endswith(")") or t.startswith("-") or t.startswith("(-")
        try:
            v = float(t.strip("()%").replace(",", "").lstrip("-").rstrip("%"))
        except ValueError:
            continue
        out.append(-v if neg else v)
    words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twelve": 12}
    out += [v for w, v in words.items() if re.search(rf"(?i)\b{w}\b", quote)]
    return out


def _value_in(text, v):
    return any(abs(n * k - v) <= 1e-6 * max(1, abs(v)) + 1e-9 for n in _numbers(text) for k in (1, 1000, 0.001, 1e6, 1e-6, 100, 0.01, 12, 1 / 12))


def _bound(op, source, user):
    """Returns '' if the operand is bound, else the reason it is not. Bound means: the quote occurs in the text it
    claims to come from; it is one short clause; the value is printed in it (allowing thousand/million/billion,
    percent and month/year rescaling); when the clause prints more than one number, the operand names verbatim
    condition words that occur in the clause next to its number; and the user words it claims to match occur in
    the user's situation."""
    text = _norm(source if op["from"] == "source" else user)
    quote = _norm(op["quote"])
    if not quote or quote not in text:
        return "quote not found in " + op["from"]
    if len(quote) > 220:
        return "quote longer than one clause"
    v, hits = op["value"], []
    for m in NUM.finditer(op["quote"]):
        for n in _numbers(m.group(0)):
            if any(abs(n * k - v) <= 1e-6 * max(1, abs(v)) + 1e-9 for k in (1, 1000, 0.001, 1e6, 1e-6, 100, 0.01, 12, 1 / 12)):
                hits.append(m.start())
    word_hit = any(abs(n - v) < 1e-9 for n in _numbers(op["quote"])) and not hits
    if not hits and not word_hit:
        return "value not printed in quote"
    distinct = {round(n, 6) for n in _numbers(op["quote"])}
    cond = op.get("condition_words", "").strip()
    if op["from"] == "source" and len(distinct) > 1:
        if not cond:
            return "clause prints several numbers but no condition words were given"
        nq, nc = _norm(op["quote"]), _norm(cond)
        if nc not in nq:
            return "condition words not in quote"
        if not _value_in(cond, v):  # words that contain the number itself are explicit
            clauses = [c for c in CLAUSE.split(nq) if c.strip()]
            at = re.compile(r"(?<![\w-])" + re.escape(nc) + r"(?![\w-])")
            home = [c for c in clauses if at.search(c)]
            ok = any(_value_in(c, v) and len({round(n, 6) for n in _numbers(c.replace(nc, " "))} | {round(n, 6) for n in _numbers(c) if abs(n - v) < 1e-9}) == 1
                     for c in home)
            if not ok:
                return "condition words are not in a clause that prints only this number"
    elif cond and _norm(cond) not in quote:
        return "condition words not in quote"
    ucond = op.get("user_condition_words", "").strip()
    if ucond and _norm(ucond) not in _norm(user):
        return "user condition words not in the user's situation"
    return ""


# Condition compatibility: a small fixed lexicon over five dimensions. Conditions are read from the clause that
# prints the number (not from words the model chose) and from the whole user situation (so leaving
# user_condition_words empty cannot bypass the check). Population scope needs judgement and is never verified.
COND = {
    "billing": [("annual", re.compile(r"(?i)\b(billed|paid|paying|pay)\s+(annually|yearly)\b|\bwhen paying annually\b|\bannual (plan|billing)\b|\bper year\b|\bevery 12 months\b|\bfor the first 12 months\b|\b/yr\b")),
                ("monthly", re.compile(r"(?i)\b(billed|paid|paying|pay)\s+monthly\b|\bwhen paying monthly\b|\bmonth[- ]to[- ]month\b|\bmonthly, with no annual\b|\bfor the first month\b"))],
    "accounting": [("non-GAAP", re.compile(r"(?i)\bnon-GAAP\b|\badjusted\b")),
                   ("GAAP", re.compile(r"(?i)(?<![\w-])GAAP\b(?! *figures? *: *non)"))],
    "period": [("year to date", re.compile(r"(?i)\bnine months\b|\bfirst-nine-months\b|\byear[- ]to[- ]date\b")),
               ("quarter", re.compile(r"(?i)\bthird quarter\b|\bthird-quarter\b|\bthree months\b|\bthe quarter\b"))],
    "effect": [("absolute", re.compile(r"(?i)\babsolute\b|\bpercentage points?\b|\bARR\b")),
               ("relative", re.compile(r"(?i)\brelative\b|\bRRR\b"))],
    "population": [("named", re.compile(r"(?i)\bpatients?\b|\bchildren\b|\bpediatric\b|\badults?\b|\byears of age\b|\bparticipants\b|\boverweight\b|\bobese\b|\bwomen\b|\bmen\b"))],
}


PER_UNIT = re.compile(r"(?i)\bper (user|seat|member|domain|person|license|GB|TB|MAU|unit)\b|/\s*(user|seat|member)\b|\bper\s+[\d,]+\b|/\s*[\d,]+\s*(emails|requests)?\b|\beach\b")


def _home(op):
    nq = _norm(op["quote"])
    clauses = [c for c in CLAUSE.split(nq) if c.strip()] or [nq]
    return " ".join([c for c in clauses if _value_in(c, op["value"])] or [nq])


def _scaled_by_user(expr, name, ops):
    """True if `name` is multiplied (directly or through a sub-expression) by something that uses a user operand."""
    import ast
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return False
    users = {k for k, o in ops.items() if o["from"] == "user"}
    names = lambda node: {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Mult, ast.Div)):
            left, right = names(node.left), names(node.right)
            if (name in left and right & users) or (name in right and left & users):
                return True
    return False


def _conditions(text):
    """{dimension: value} for the dimensions the text states. GAAP is only GAAP when non-GAAP is absent."""
    out = {}
    for dim, options in COND.items():
        found = [val for val, rx in options if rx.search(text)]
        if dim == "accounting" and "non-GAAP" in found:
            found = ["non-GAAP"] if not re.search(r"(?i)(?<![\w-])GAAP\b", re.sub(r"(?i)non-GAAP", "", text)) else found
        if len(found) == 1:
            out[dim] = found[0]
        elif len(found) > 1:
            out[dim] = "mixed"
    return out


def _compatible(op, source, user):
    """'' if the operand's printed conditions are verified to match the user's situation; else the reason.
    Only for source operands. Uses the clause that prints the number."""
    if op["from"] != "source":
        return ""
    nq = _norm(op["quote"])
    clauses = [c for c in CLAUSE.split(nq) if c.strip()] or [nq]
    home = [c for c in clauses if _value_in(c, op["value"])] or [nq]
    printed = _conditions(" ".join(home))
    wanted = _conditions(user)
    for dim, val in printed.items():
        if dim == "population":
            return "population scope cannot be verified by code"
        if val == "mixed":
            return f"{dim}: the clause states more than one condition"
        if dim not in wanted:
            return f"{dim}: printed '{val}' but the user's situation does not state one"
        if wanted[dim] != val:
            return f"{dim}: printed '{val}' conflicts with the user's '{wanted[dim]}'"
    if op.get("condition_words", "").strip() and not printed and not PER_UNIT.search(" ".join(home)):
        return "printed condition not in the verifiable lexicon"
    return ""


def _evaluate(expr, env):
    import ast
    tree = ast.parse(expr, mode="eval")
    allowed = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.USub, ast.UAdd, ast.Constant,
               ast.Name, ast.Load, ast.Call)
    for node in ast.walk(tree):
        if not isinstance(node, allowed):
            raise ValueError(f"disallowed syntax {type(node).__name__}")
        if isinstance(node, ast.Call) and not (isinstance(node.func, ast.Name) and node.func.id in ("max", "min")):
            raise ValueError("only max/min calls")
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float)):
            raise ValueError("non-numeric constant")
    return float(eval(compile(tree, "<expr>", "eval"), {"__builtins__": {}, "max": max, "min": min}, env))


def qbr_decide(out, item, case, policy="bound_first"):
    """policy: bound_first = code's recomputation when every operand is bound, else the judge's verdict;
    agree = intervene only when code and judge agree, defer ('insufficient') on disagreement;
    judge_only = the judge's own verdict (the structured-output checklist judge)."""
    said = _verdict_word(case["answer"])
    judge = {"correct": "correct", "wrong": "incorrect", "cannot tell from the source": "insufficient"}[out["recommendation_for_this_user"]]
    trace = {"qbr": out}
    if policy == "judge_only":
        return {"verdict": judge, "trace": trace}
    if out["quoted_value_applies_to_user"] == "no printed value applies to this user":
        return {"verdict": "insufficient", "trace": dict(trace, used="insufficient")}
    ops = {o["name"]: o for o in out["operands"]}
    reasons = {o["name"]: _bound(o, item["excerpt"], case["context"]) or _compatible(o, item["excerpt"], case["context"]) for o in out["operands"]}
    if out["limit_operand"] in ops and ops[out["limit_operand"]]["from"] != "user":
        reasons[out["limit_operand"]] = reasons.get(out["limit_operand"]) or "limit not taken from the user"
    for k, o in ops.items():  # a per-unit price must be scaled by the user's quantity in the computation
        if not reasons.get(k) and o["from"] == "source" and PER_UNIT.search(_home(o)) and not _scaled_by_user(out["user_value_expression"], k, ops):
            reasons[k] = "per-unit value not multiplied by a user quantity"
    import ast
    try:  # only operands the computation actually uses (and the limit) must be verified
        used = {n.id for n in ast.walk(ast.parse(out["user_value_expression"], mode="eval")) if isinstance(n, ast.Name)} | {out["limit_operand"]}
    except SyntaxError:
        used = set(ops)
    unbound = [k for k, r in reasons.items() if r and k in used]
    trace["bind_reasons"] = {k: r for k, r in reasons.items() if r and k in used}
    try:
        value = _evaluate(out["user_value_expression"], {k: o["value"] for k, o in ops.items()})
        limit = ops[out["limit_operand"]]["value"]
        ok = value <= limit + 1e-9 if out["direction"] == "at most" else value >= limit - 1e-9
        code = "correct" if ok == said else "incorrect"
        trace.update(user_value=value, limit=limit, decision=ok, unbound=unbound)
    except Exception as exc:  # unusable computation: fall back to the judge, recorded
        trace.update(error=repr(exc)[:200], unbound=unbound)
        return {"verdict": judge, "trace": dict(trace, used="judge (computation unusable)")}
    if out["limit_operand"] not in ops:
        return {"verdict": judge, "trace": dict(trace, used="judge (computation unusable)")}
    if unbound:
        return {"verdict": judge, "trace": dict(trace, used="judge (operand not verified)")}
    if policy == "agree" and code != judge:
        return {"verdict": "insufficient", "trace": dict(trace, used="defer (code and judge disagree)")}
    if policy == "source_bound":  # v3 requirement, fixed before any v3 run: the computation must use the evidence
        try:
            names = {n.id for n in ast.walk(ast.parse(out["user_value_expression"], mode="eval")) if isinstance(n, ast.Name)}
        except SyntaxError:
            names = set()
        if not any(ops[k]["from"] == "source" for k in names if k in ops):
            return {"verdict": judge, "trace": dict(trace, used="judge (computation uses no source value)")}
    return {"verdict": code, "trace": dict(trace, used="code")}


def qbr(item, case, policy="bound_first"):
    msgs = _judge_messages(item, case, True)
    msgs[0]["content"] += QBR_INSTRUCTIONS
    out, rec = _call(msgs, QBR_SCHEMA, max_tokens=3600)
    if out is None:
        return {"verdict": "error", "corrected": "", "calls": [rec]}
    res = qbr_decide(out, item, case, policy)
    res.update(corrected=res["trace"].get("used", ""), raw=out, calls=[rec])
    return res


# ---------------------------------------------------------------- prevalence: the model answers by itself
DIRECT_SCHEMA = _obj({"reason": {"type": "string"}, "answer": _enum("yes", "no", "insufficient evidence")})


def _question(item, case):
    head = case["answer"].split(".")[0].replace("Recommendation: ", "")
    if item["domain"] == "science":
        return "Based on this source, does the evidence show the treatment meets my bar?"
    m = re.match(r"(.+?) (fits|passes|fails) your (limit|screen)", head)
    name = re.sub(r"^(A|This) ", lambda w: w[0].lower(), m[1])
    return f"Based on this source, does {name} {'fit my limit' if m[3] == 'limit' else 'pass my screen'}?"


def direct(item, case):
    msg = [{"role": "system", "content": "Answer the user's question from the source excerpt. Answer 'insufficient evidence' if the source does not establish the answer for this user."},
           {"role": "user", "content": f"SOURCE EXCERPT ({item['source'][0]}):\n{item['excerpt']}\n\nMY SITUATION:\n{case['context']}\n\nQUESTION: {_question(item, case)}"}]
    out, rec = _call(msg, DIRECT_SCHEMA, max_tokens=2000)
    if out is None:
        return {"verdict": "error", "corrected": "", "calls": [rec]}
    truth = case["gold"]["correct_recommendation"]
    gold_yes = truth in ("fits", "passes", "yes")
    gold_ans = "insufficient evidence" if truth.startswith("insufficient") else ("yes" if gold_yes else "no")
    return {"verdict": "correct" if out["answer"] == gold_ans else "incorrect", "corrected": out["answer"], "raw": out, "calls": [rec]}


# ---------------------------------------------------------------- v3: assistants write the cited answers
ASSIST_SYSTEM = ("You are a helpful assistant. Answer the user's question using only the source excerpt. "
                 "Explain briefly, quote the exact text from the source that your answer relies on, and give a clear decision.")


def assist(item, case, endpoint, alias, max_tokens=700):
    """One natural cited answer from an assistant model (temperature 0, fixed seed, JSON schema)."""
    yes, no = item["decision_options"]
    schema = _obj({"explanation": {"type": "string"}, "quote": {"type": "string"}, "decision": _enum(yes, no)})
    msgs = [{"role": "system", "content": ASSIST_SYSTEM},
            {"role": "user", "content": f"SOURCE EXCERPT ({item['source'][0]}):\n{item['excerpt']}\n\nMY SITUATION:\n{case['context']}\n\n"
                                        f"QUESTION: {item['question']} Answer '{yes}' or '{no}'."}]
    body = {"model": alias, "messages": msgs, "temperature": 0, "seed": SEED, "max_tokens": max_tokens,
            "response_format": {"type": "json_schema", "json_schema": {"name": "out", "strict": True, "schema": schema}}}
    req = urllib.request.Request(endpoint.rstrip("/") + "/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    started = time.perf_counter()
    raw = json.loads(urllib.request.urlopen(req, timeout=900).read())
    record = {"messages": msgs, "response": raw, "seconds": round(time.perf_counter() - started, 2)}
    try:
        return json.loads(raw["choices"][0]["message"]["content"]), record
    except ValueError:
        return None, record


def answer_text(item, out):
    """The assistant's answer in the form verifiers receive: decision first, then its explanation and quote."""
    yes, no = item["decision_options"]
    if item["domain"] == "finance":
        head = f"Recommendation: {item['subject']} {'passes' if out['decision'] == yes else 'fails'} your screen."
    else:
        head = f"Recommendation: {'yes' if out['decision'] == yes else 'no'}, the evidence {'meets' if out['decision'] == yes else 'does not meet'} your bar for {item['subject']}."
    return f"{head} {out['explanation'].strip()} (\u201c{out['quote'].strip()}\u201d)"


ARMS = {"qbr": lambda i, c, cache: qbr(i, c), "direct": lambda i, c, cache: direct(i, c), "judge": lambda i, c, cache: judge(i, c, False), "judge_checklist": lambda i, c, cache: judge(i, c, True),
        "rules": lambda i, c, cache: rules(i, c), "dcv": lambda i, c, cache: dcv(i, c, cache)}
