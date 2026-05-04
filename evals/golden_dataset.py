"""
Golden dataset for PR review evaluation.
100 labeled cases are the Phase 3 target; this ships the critical seed set.
New cases added via: evals/add_case.py --category security --id sql-002 --diff <file>
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EvalCase:
    id: str
    category: str           # security | performance | style | false_positive
    diff: str
    expected_flags: list[str]
    expected_severity: str  # critical | high | medium | low | none
    description: str = ""


GOLDEN_CASES: list[EvalCase] = [
    # ── Security ──────────────────────────────────────────────────────────
    EvalCase(
        id="security-sql-001",
        category="security",
        diff="""
-def get_user(user_id):
-    return db.execute("SELECT * FROM users WHERE id = " + user_id)
+def get_user(user_id):
+    return db.execute("SELECT * FROM users WHERE id = %s", (user_id,))
""",
        expected_flags=["sql_injection"],
        expected_severity="critical",
        description="Raw string concatenation in SQL query — classic SQLi",
    ),
    EvalCase(
        id="security-auth-001",
        category="security",
        diff="""
-def get_account(account_id, user_id):
-    return Account.find(account_id)
+def get_account(account_id, user_id):
+    account = Account.find(account_id)
+    raise_unless account.owner_id == user_id
+    return account
""",
        expected_flags=["missing_auth", "insecure_direct_object_ref"],
        expected_severity="high",
        description="IDOR — account lookup without ownership check",
    ),
    EvalCase(
        id="security-ssrf-001",
        category="security",
        diff="""
+def fetch_avatar(url):
+    return requests.get(url).content
""",
        expected_flags=["ssrf"],
        expected_severity="high",
        description="SSRF — user-supplied URL fetched without validation",
    ),
    EvalCase(
        id="security-secret-001",
        category="security",
        diff="""
+API_KEY = "sk-prod-abc123def456"
+STRIPE_SECRET = "sk_live_xyz789"
""",
        expected_flags=["hardcoded_secret", "credential_exposure"],
        expected_severity="critical",
        description="Production secrets committed to source",
    ),

    # ── Performance ────────────────────────────────────────────────────────
    EvalCase(
        id="perf-n+1-001",
        category="performance",
        diff="""
+for order in Order.all():
+    customer = Customer.find(order.customer_id)
+    print(customer.email)
""",
        expected_flags=["n_plus_1_query"],
        expected_severity="medium",
        description="N+1 query — Customer.find inside a loop over all Orders",
    ),
    EvalCase(
        id="perf-memory-001",
        category="performance",
        diff="""
+def process_logs():
+    all_logs = Log.all()   # loads entire table into memory
+    return [l for l in all_logs if l.level == 'ERROR']
""",
        expected_flags=["memory_exhaustion", "missing_pagination"],
        expected_severity="medium",
        description="Loading unbounded table into memory",
    ),

    # ── Style ──────────────────────────────────────────────────────────────
    EvalCase(
        id="style-magic-001",
        category="style",
        diff="""
-timeout = config.get('timeout')
+timeout = 30
""",
        expected_flags=["magic_number"],
        expected_severity="low",
        description="Magic number — 30 should be a named constant",
    ),
    EvalCase(
        id="style-error-handling-001",
        category="style",
        diff="""
+try:
+    result = risky_operation()
+except Exception:
+    pass
""",
        expected_flags=["swallowed_exception"],
        expected_severity="medium",
        description="Bare except swallows all errors silently",
    ),

    # ── False positives (should NOT flag) ──────────────────────────────────
    EvalCase(
        id="fp-parameterized-001",
        category="false_positive",
        diff="""
+def get_user(user_id):
+    return db.execute("SELECT * FROM users WHERE id = %s", (user_id,))
""",
        expected_flags=[],
        expected_severity="none",
        description="Correct parameterized query — must NOT flag as SQLi",
    ),
    EvalCase(
        id="fp-test-constant-001",
        category="false_positive",
        diff="""
+TEST_TIMEOUT_SECONDS = 30
+MAX_RETRIES = 3
""",
        expected_flags=[],
        expected_severity="none",
        description="Named constants in test file — must NOT flag as magic numbers",
    ),
]

REQUIRED_CATEGORIES = {"security", "performance", "style", "false_positive"}
