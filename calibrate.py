"""Run the calibration set against a live server and print one block per case."""

import json
import os
import urllib.error
import urllib.request

API = f"http://localhost:{os.getenv('PORT', '5050')}"

CASES = [
    (
        "1 AI-like formal",
        "test-ai",
        "Artificial intelligence represents a transformative paradigm shift in modern society. "
        "It is important to note that while the benefits of AI are numerous, it is equally "
        "essential to consider the ethical implications. Furthermore, stakeholders across "
        "various sectors must collaborate to ensure responsible deployment. In today's society, "
        "organizations play a crucial role in establishing frameworks that balance innovation "
        "with accountability. Overall, a wide range of considerations must inform any strategy "
        "going forward.",
    ),
    (
        "2 casual human",
        "test-human",
        "ok so i finally tried that new ramen place downtown and honestly? underwhelming. the "
        "broth was fine but they put WAY too much sodium in it and i was thirsty for like three "
        "hours after. my friend got the spicy version and said it was better. probably won't go "
        "back unless someone drags me there",
    ),
    (
        "3 formal human",
        "test-formal",
        "The relationship between monetary policy and asset price inflation has been extensively "
        "studied in the literature. Central banks face a fundamental tension between their "
        "mandate for price stability and the unintended consequences of prolonged low interest "
        "rates on equity and real estate valuations. Empirical work since 2008 suggests the "
        "transmission channel runs through portfolio rebalancing rather than direct credit "
        "expansion, though the magnitude remains contested across national contexts.",
    ),
    (
        "4 hybrid edited",
        "test-hybrid",
        "I've been thinking a lot about remote work lately. There are genuine tradeoffs, "
        "flexibility and no commute on one side, isolation and blurred work-life boundaries on "
        "the other. Studies show productivity varies widely by individual and role type. In my "
        "own experience the hardest part has been the loss of incidental conversation, the small "
        "unplanned exchanges that used to happen near the coffee machine and now need a calendar "
        "invite.",
    ),
    (
        "5 non-native formal",
        "test-nonnative",
        "I am working in the field of civil engineering since eight years. My responsibility is "
        "to check the drawings and to make sure that the site team follow the specification. "
        "Last month we have completed the drainage work for the north sector. The client was "
        "satisfied with the result and asked us to continue with the next phase of the project.",
    ),
    ("6 short text", "test-short", "I liked it."),
    (
        "7 poetic",
        "test-poetic",
        "The window kept the rain like a secret. I kept my coat on indoors. Nobody asked why.",
    ),
]


def submit(text, creator_id):
    body = json.dumps({"text": text, "creator_id": creator_id}).encode()
    req = urllib.request.Request(
        f"{API}/submit", data=body, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.load(resp)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


for name, creator_id, text in CASES:
    print(f"=== {name} ===")
    status, d = submit(text, creator_id)
    if status != 201:
        print(f"  HTTP {status}: {d}")
        print()
        continue
    s = d["signals"]
    print(
        f"  llm={s['llm']['score']}  sty={s['stylometry']['score']}  spec={s['specificity']['score']}"
    )
    print(
        f"  ai_likelihood={d['ai_likelihood']}  agreement={d['signal_agreement']}  confidence={d['confidence']}"
    )
    print(f"  attribution={d['attribution']}")
    print(f"  reason: {s['llm']['reason']}")
    print(f"  content_id={d['content_id']}")
    print()
