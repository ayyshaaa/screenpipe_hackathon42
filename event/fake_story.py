#!/usr/bin/env python3
"""SYNTHETIC screen history: Inès, product manager at Tavola, 7 Sep - 6 Oct 2026.

Writes fake_data/story.json:
  captures: list of screenpipe-shaped results ({"type": "OCR"|"UI", "content": {...}})
  truth:    source_id -> label (category, task, step, run, kind). Scoring only, never pipeline input.

Hidden repeated tasks (what CONCENTRATION should find, in this order by observed minutes):
  weekly_report    5 Monday runs, ~25 min. Run 3: one-off expired-login detour (troubleshooting).
                   From run 4: extra "Lyon tab" step (process change, still normal).
  refund_check     20 morning runs, ~4 min. One EUR 64.80 refund escalated (exception).
  partner_onboard  4 runs, ~19 min. Sushi Kan has no SIRET (exception).
Not tasks: Monday squad sync (meeting, classic false positive), project work, one-offs, noise.
"""
import os
import random
from datetime import date, datetime, timedelta, timezone

from common import LOCAL_TZ, iso, write_json

SEED = 42
START, END = date(2026, 9, 7), date(2026, 10, 6)
OUT = "fake_data/story.json"

# ---------- step templates: (step key, app, window, url, minutes, [screen lines]) ----------
# {placeholders} are filled per run so dates and numbers change, like real weeks.

WEEKLY = [
    ("dashboard", "Google Chrome", "Orders overview – Metabase", "https://metabase.tavola.fr/dashboard/12", 5,
     ["Orders overview week {week} | Last 7 days | Paris + Lyon",
      "Orders {orders} | Revenue €{revenue} | Avg basket €{basket}",
      "Filter: last 7 days, all cities, status = delivered"]),
    ("export", "Google Chrome", "Export results – Metabase", "https://metabase.tavola.fr/question/88", 4,
     ["Download full results | orders_week_{week}.csv",
      "Export complete: {orders} rows, 14 columns",
      "Saved to Downloads/orders_week_{week}.csv"]),
    ("sheet", "Google Chrome", "Weekly KPI report – Google Sheets", "https://docs.google.com/spreadsheets/d/kpi", 9,
     ["Weekly KPI report | tab Week {week} | paste orders_week_{week}.csv",
      "Total orders {orders} | Revenue €{revenue} | vs last week {delta}%",
      "Update chart: revenue by day, week {week}"]),
    ("lyon", "Google Chrome", "Weekly KPI report – Lyon – Google Sheets", "https://docs.google.com/spreadsheets/d/kpi#lyon", 4,
     ["Lyon tab | week {week} | orders Lyon {lyon}",
      "City breakdown added: Paris {paris} / Lyon {lyon}"]),
    ("email", "Google Chrome", "Weekly KPI report – Gmail", "https://mail.google.com/mail/u/0/#compose", 5,
     ["To: leadership@tavola.fr | Subject: Weekly KPI report – week {week}",
      "Hi all, here is the weekly report for week {week}: {orders} orders, €{revenue} revenue.",
      "Attachment: Weekly KPI report week {week}.pdf | Sent"]),
]
WEEKLY_DETOUR = ("login_detour", "Google Chrome", "Sign in – Tavola SSO", "https://sso.tavola.fr/login", 6,
                 ["Your session has expired. Please sign in again.",
                  "Password expired – choose a new password (12 characters minimum)",
                  "Password updated. Redirecting to Metabase…"])

REFUND = [
    ("queue", "Google Chrome", "Refund requests – Zendesk", "https://tavola.zendesk.com/agent/filters/refunds", 1.3,
     ["Refund requests | {open} open | oldest ticket #{ticket}",
      "#{ticket} {customer}: refund request order TAV-{order}"]),
    ("stripe", "Google Chrome", "Payments – Stripe", "https://dashboard.stripe.com/payments", 1.3,
     ["Search: TAV-{order} | €{amount} | Succeeded",
      "Refund €{amount} to {customer} | Refund issued"]),
    ("reply", "Google Chrome", "Ticket #{ticket} – Zendesk", "https://tavola.zendesk.com/agent/tickets/{ticket}", 1.2,
     ["Macro: Refund confirmed | Hello {customer}, your refund of €{amount} is on its way.",
      "Ticket #{ticket} status: Solved"]),
]
REFUND_ESCALATION = ("escalation", "Google Chrome", "Escalate refund – Zendesk", "https://tavola.zendesk.com/agent/tickets/{ticket}/escalate", 1.5,
                     ["Refund €64.80 exceeds the €50 auto-approval limit",
                      "Escalated to Finance | assignee: Finance team | priority: normal"])

PARTNER = [
    ("application", "Google Chrome", "New partner application – Gmail", "https://mail.google.com/mail/u/0/#inbox", 3,
     ["New partner application: {restaurant} ({city})",
      "Contact: {contact} | cuisine: {cuisine} | 2 locations"]),
    ("siret", "Google Chrome", "Pappers – {restaurant}", "https://www.pappers.fr/recherche?q={restaurant}", 3,
     ["Search company: {restaurant}",
      "SIRET {siret} | {restaurant} SAS | status: active"]),
    ("admin", "Google Chrome", "Partners – Tavola Admin", "https://admin.tavola.fr/partners/new", 8,
     ["Create partner: {restaurant} | city {city} | commission 15%",
      "Menu upload: {dishes} dishes imported | photos pending",
      "Partner {restaurant} saved with SIRET {siret}"]),
    ("checklist", "Notion", "Partner onboarding checklist – Notion", "", 4,
     ["Onboarding checklist – {restaurant}",
      "Contract sent ✓ | Menu ✓ | Bank details ✓ | Go-live date {golive}"]),
]
PARTNER_MISSING_SIRET = ("ask_siret", "Google Chrome", "Request SIRET – Gmail", "https://mail.google.com/mail/u/0/#compose", 3,
                         ["To: {contact} | Subject: SIRET number needed for Tavola onboarding",
                          "Hello, we could not find a SIRET for {restaurant}. Could you send it so we can finish your onboarding?"])
PARTNERS = [
    dict(restaurant="Le Petit Zinc", city="Paris", contact="claire@petitzinc.fr", cuisine="bistro", siret="812 345 678 00019", dishes=24),
    dict(restaurant="Mamma Rosa", city="Lyon", contact="rosa@mammarosa.it", cuisine="italian", siret="790 112 334 00027", dishes=31),
    dict(restaurant="Sushi Kan", city="Paris", contact="kan@sushikan.fr", cuisine="japanese", siret="pending", dishes=40),
    dict(restaurant="La Cantine Verte", city="Lyon", contact="hello@cantineverte.fr", cuisine="vegan", siret="853 990 101 00011", dishes=18),
]

SQUAD = [
    ("call", "Google Chrome", "Squad sync – Google Meet", "https://meet.google.com/tav-squad", 25,
     ["Squad sync | Inès, Karim, Léa, Tom | sprint {sprint}",
      "Karim: checkout bug fixed | Léa: Lyon launch blockers | Tom: on-call"]),
    ("notes", "Notion", "Squad sync notes – Notion", "", 5,
     ["Squad sync – sprint {sprint} – notes",
      "Action items: Karim → release notes, Léa → Lyon courier contract"]),
]

PROJECT = [
    ("Figma", "Menu redesign – Figma", ["Menu redesign v{v} | frame: dish card", "Comment from Léa: bigger photos?", "Prototype flow: menu → dish → basket"]),
    ("Notion", "Menu redesign spec – Notion", ["Menu redesign spec v{v}", "Open question: allergens icons?", "Success metric: add-to-basket rate"]),
    ("Google Chrome", "Dovetail – Menu interviews", ["Interview notes #{v}: users scroll past photos", "Tag: navigation pain"]),
]

ONE_OFFS = [
    ("Google Chrome", "Q4 pricing deck – Google Slides", ["Q4 pricing proposal | slide 4 | delivery fee scenarios"], 35),
    ("Google Chrome", "Offsite Lisbon – Booking.com", ["Hotel Lisboa Centro | 12 rooms | 22–24 Oct"], 12),
    ("Spendesk", "Expense report September – Spendesk", ["Expense report September | 6 receipts | €212.40"], 15),
    ("Google Chrome", "Candidate interview – Google Meet", ["Interview: Product designer | portfolio review"], 45),
    ("Google Chrome", "Bug TAV-2231 – Jira", ["TAV-2231 Checkout fails on Safari 17 | priority high"], 10),
    ("Notion", "Salesforce migration notes – Notion", ["Salesforce → HubSpot migration | field mapping"], 25),
]

NOISE = [
    ("Slack", "#general – Slack", ["{who}: lunch at 12:30?", "{who}: who has the HDMI adapter", "{who}: 🎉 welcome to our new courier lead", "{who}: office closes early Friday"]),
    ("Slack", "#product – Slack", ["{who}: release 4.{n} is live", "{who}: can someone check the Lyon map?", "{who}: retro moved to Thursday"]),
    ("Slack", "Karim – Slack", ["Karim: did you see the checkout numbers?", "Karim: coffee?", "Karim: PR is ready for review"]),
    ("Mail", "Inbox – Mail", ["Inbox ({n}) | Newsletter: Lenny's | Calendar: 1:1 with Sarah", "Inbox ({n}) | Invoice from Notion | Webinar reminder"]),
    ("Spotify", "Spotify Premium", ["Now playing: {song}", "Focus Flow playlist | {song}"]),
]
SONGS = ["Nils Frahm – Says", "Bonobo – Kerala", "Air – La femme d'argent", "Khruangbin – Maria También", "Tycho – Awake"]
WHO = ["Léa", "Tom", "Sarah", "Karim", "Nadia"]


class Story:
    def __init__(self):
        self.rng = random.Random(SEED)
        self.captures, self.truth = [], {}
        self.frame_id, self.ui_id = 1000, 1

    def add_session(self, start_local, minutes, app, window, url, lines, label):
        """One intended session: a screenshot every ~40 s + one accessibility (UI) capture."""
        t = start_local
        end = start_local + timedelta(minutes=minutes)
        i = 0
        while t <= end:
            text = lines[i % len(lines)]
            sid = f"ocr:{self.frame_id}"
            self.captures.append({"type": "OCR", "content": {
                "frame_id": self.frame_id, "text": text, "timestamp": iso(t), "app_name": app,
                "window_name": window, "browser_url": url, "focused": True, "file_path": "", "offset_index": 0,
                "tags": [], "device_name": "laptop"}})
            self.truth[sid] = label
            self.frame_id += 1
            i += 1
            t += timedelta(seconds=self.rng.randint(30, 50))
        # the accessibility tree often shows the same text as OCR: tests "count duplicates once"
        mid = start_local + timedelta(minutes=minutes / 2)
        sid = f"ui:{self.ui_id}"
        self.captures.append({"type": "UI", "content": {
            "id": self.ui_id, "text": lines[0], "timestamp": iso(mid), "app_name": app,
            "window_name": window, "browser_url": url, "file_path": "", "offset_index": 0}})
        self.truth[sid] = label
        self.ui_id += 1
        return start_local + timedelta(minutes=minutes)

    def run_steps(self, start, steps, values, task, run, kinds=None, category="task", gap=(0.2, 0.8)):
        """Play steps back to back. Returns (start, end) so noise is not placed inside the run."""
        t = start
        for key, app, window, url, minutes, lines in steps:
            kind = (kinds or {}).get(key, "normal") if category == "task" else None
            label = {"category": category, "task": task, "step": key, "run": run, "kind": kind}
            if kind == "noise":  # an interruption inside a run, not part of the task
                label = {"category": "noise", "task": None, "step": key, "run": None, "kind": None}
            minutes = minutes * self.rng.uniform(0.85, 1.15)
            t = self.add_session(t, minutes, app, window.format(**values), url.format(**values),
                                 [l.format(**values) for l in lines], label)
            t += timedelta(minutes=self.rng.uniform(*gap))
        return start, t


def local(d, hh, mm):
    return datetime(d.year, d.month, d.day, hh, mm, tzinfo=LOCAL_TZ).astimezone(timezone.utc)


def build():
    st = Story()
    rng = st.rng
    days = [START + timedelta(n) for n in range((END - START).days + 1)]
    workdays = [d for d in days if d.weekday() < 5]
    mondays = [d for d in workdays if d.weekday() == 0]
    refund_days = [d for i, d in enumerate(workdays) if i not in (6, 15)]  # 20 runs
    escalation_day = refund_days[9]
    partner_days = [date(2026, 9, 10), date(2026, 9, 17), date(2026, 9, 24), date(2026, 10, 1)]
    project_days = rng.sample([d for d in workdays if d not in mondays], 9)
    one_off_days = rng.sample(workdays, len(ONE_OFFS))
    busy = {d: [] for d in days}  # (start, end) spans where noise must not land

    for n, d in enumerate(refund_days):
        values = dict(open=rng.randint(3, 11), ticket=48210 + n * 37, customer=rng.choice(["M. Durand", "J. Martin", "A. Petit", "S. Moreau"]),
                      order=91000 + n * 113, amount=f"{rng.uniform(8, 45):.2f}")
        steps, kinds = list(REFUND), {}
        if d == escalation_day:
            values["amount"] = "64.80"
            steps.insert(2, REFUND_ESCALATION)
            kinds = {"escalation": "exception"}
        run = f"refund_check-{d.isoformat()}"
        busy[d].append(st.run_steps(local(d, 9, rng.randint(2, 20)), steps, values, "refund_check", run, kinds))

    for n, d in enumerate(mondays):
        sprint = 41 + n
        # recurring meeting: same steps every Monday, but NOT a task to automate
        busy[d].append(st.run_steps(local(d, 9, 30), SQUAD, {"sprint": sprint}, None, None, category="meeting"))

        orders = rng.randint(2100, 2900)
        lyon = rng.randint(300, 600)
        values = dict(week=37 + n, orders=orders, revenue=f"{orders * rng.uniform(27, 31):,.0f}".replace(",", " "),
                      basket=f"{rng.uniform(27, 31):.2f}", delta=f"{rng.uniform(-6, 9):+.1f}", lyon=lyon, paris=orders - lyon)
        steps = [s for s in WEEKLY if s[0] != "lyon" or n >= 3]  # Lyon tab only from run 4
        kinds = {}
        if n == 1:  # run 2: a Slack message interrupts the run (noise inside a run, reviewer removes it)
            steps.insert(3, ("slack_popup", "Slack", "#general – Slack", "", 0.7, ["Léa: is the weekly report out yet?"]))
            kinds = {"slack_popup": "noise"}
        if n == 2:  # run 3: expired login before the export
            steps.insert(1, WEEKLY_DETOUR)
            kinds = {"login_detour": "troubleshooting"}
        run = f"weekly_report-{d.isoformat()}"
        busy[d].append(st.run_steps(local(d, 14, rng.randint(0, 15)), steps, values, "weekly_report", run, kinds))

    for p, d in zip(PARTNERS, partner_days):
        values = dict(p, golive=(d + timedelta(14)).isoformat())
        steps, kinds = list(PARTNER), {}
        if p["restaurant"] == "Sushi Kan":
            steps[1] = ("siret", PARTNER[1][1], PARTNER[1][2], PARTNER[1][3], 3,
                        ["Search company: {restaurant}", "Aucun résultat – no SIRET found for {restaurant}"])
            steps.insert(2, PARTNER_MISSING_SIRET)
            kinds = {"ask_siret": "exception"}
        run = f"partner_onboard-{d.isoformat()}"
        busy[d].append(st.run_steps(local(d, 15, rng.randint(20, 40)), steps, values, "partner_onboard", run, kinds))

    for v, d in enumerate(project_days):
        t = local(d, 11, rng.randint(0, 30))
        for app, window, lines in rng.sample(PROJECT, rng.randint(1, 3)):
            mins = rng.uniform(8, 30)
            t = st.add_session(t, mins, app, window, "", [l.format(v=v + 2) for l in rng.sample(lines, len(lines))],
                               {"category": "project", "task": None, "step": window, "run": None, "kind": None})
            t += timedelta(minutes=rng.uniform(2, 10))
        busy[d].append((local(d, 11, 0), t))

    for (app, window, lines, mins), d in zip(ONE_OFFS, one_off_days):
        t = local(d, 16, rng.randint(30, 59))
        st.add_session(t, mins, app, window, "", lines, {"category": "one_off", "task": None, "step": window, "run": None, "kind": None})
        busy[d].append((t, t + timedelta(minutes=mins)))

    for d in days:
        n_noise = rng.randint(6, 10) if d.weekday() < 5 else rng.randint(0, 2)
        for _ in range(n_noise):
            for _try in range(50):
                t = local(d, 8, 30) + timedelta(minutes=rng.uniform(0, 600))
                mins = rng.uniform(0.5, 3)
                margin = timedelta(minutes=6)
                if all(t + timedelta(minutes=mins) < s - margin or t > e + margin for s, e in busy[d]):
                    break
            else:
                continue
            app, window, lines = rng.choice(NOISE)
            text = rng.choice(lines).format(who=rng.choice(WHO), n=rng.randint(2, 40), song=rng.choice(SONGS))
            st.add_session(t, mins, app, window, "", [text], {"category": "noise", "task": None, "step": app.lower(), "run": None, "kind": None})
            busy[d].append((t, t + timedelta(minutes=mins)))

    st.captures.sort(key=lambda c: c["content"]["timestamp"])
    return {
        "meta": {"synthetic": True, "person": "Inès, product manager at Tavola", "from": START.isoformat(), "to": END.isoformat(),
                 "expected_ranking": ["weekly_report", "refund_check", "partner_onboard"],
                 "expected_runs": {"weekly_report": 5, "refund_check": 20, "partner_onboard": 4}},
        "captures": st.captures,
        "truth": st.truth,
    }


def main():
    story = build()
    os.makedirs("fake_data", exist_ok=True)
    write_json(OUT, story)
    print(f"wrote {OUT}: {len(story['captures'])} captures (SYNTHETIC)")


if __name__ == "__main__":
    main()
