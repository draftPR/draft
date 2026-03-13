"""Create demo data for PR review flow."""
import sqlite3
import uuid
import os
from datetime import datetime, timezone

DB = "kanban.db"
BOARD_ID = "40c6e796-b75d-47d0-9e9d-ea525b70e271"
TICKET_ID = "8b383839-cbec-45af-86ee-c7708d075cbe"  # JWT auth ticket
GOAL_ID = "d1213e05-a49c-4b30-8033-64de449e587f"

conn = sqlite3.connect(DB)
c = conn.cursor()

# 1. Transition ticket to needs_human
c.execute("UPDATE tickets SET state = ? WHERE id = ?", ("needs_human", TICKET_ID))

# 2. Create a Job record
job_id = str(uuid.uuid4())
now = datetime.now(timezone.utc).isoformat()
c.execute(
    """INSERT INTO jobs (id, ticket_id, board_id, kind, status, created_at, started_at, finished_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
    (job_id, TICKET_ID, BOARD_ID, "execute", "succeeded", now, now, now),
)

# 3. Create evidence files on disk
evidence_dir = os.path.join(".smartkanban", "evidence", TICKET_ID)
os.makedirs(evidence_dir, exist_ok=True)

diff_stat = """ src/middleware/auth.js | 45 +++++++++++++++++++++++++++++++++++++++++++++
 src/routes/auth.js    | 78 ++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
 src/models/db.js      | 12 ++++++++++--
 src/index.js          |  8 ++++++--
 package.json          |  4 +++-
 5 files changed, 142 insertions(+), 5 deletions(-)"""

diff_patch = '''diff --git a/package.json b/package.json
index 1a2b3c4..5d6e7f8 100644
--- a/package.json
+++ b/package.json
@@ -10,7 +10,9 @@
   "dependencies": {
     "express": "^4.18.2",
     "better-sqlite3": "^9.4.3",
-    "cors": "^2.8.5"
+    "cors": "^2.8.5",
+    "jsonwebtoken": "^9.0.2",
+    "bcryptjs": "^2.4.3"
   },
   "devDependencies": {
     "jest": "^29.7.0",
diff --git a/src/models/db.js b/src/models/db.js
index 2b3c4d5..8e9f0a1 100644
--- a/src/models/db.js
+++ b/src/models/db.js
@@ -8,6 +8,16 @@ db.exec(`
   )
 `);

+db.exec(`
+  CREATE TABLE IF NOT EXISTS users (
+    id INTEGER PRIMARY KEY AUTOINCREMENT,
+    username TEXT UNIQUE NOT NULL,
+    password TEXT NOT NULL,
+    email TEXT,
+    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
+  )
+`);
+
 module.exports = db;
diff --git a/src/middleware/auth.js b/src/middleware/auth.js
new file mode 100644
index 0000000..3f4a5b6
--- /dev/null
+++ b/src/middleware/auth.js
@@ -0,0 +1,45 @@
+const jwt = require("jsonwebtoken");
+
+const JWT_SECRET = process.env.JWT_SECRET || "dev-secret-key";
+
+function authenticateToken(req, res, next) {
+  const authHeader = req.headers["authorization"];
+  const token = authHeader && authHeader.split(" ")[1];
+
+  if (!token) {
+    return res.status(401).json({ error: "Access token required" });
+  }
+
+  try {
+    const decoded = jwt.verify(token, JWT_SECRET);
+    req.user = decoded;
+    next();
+  } catch (err) {
+    return res.status(401).json({ error: "Invalid or expired token" });
+  }
+}
+
+function generateToken(user) {
+  return jwt.sign(
+    { id: user.id, username: user.username },
+    JWT_SECRET,
+    { expiresIn: "24h" }
+  );
+}
+
+function hashPassword(password) {
+  const bcrypt = require("bcryptjs");
+  return bcrypt.hashSync(password, 10);
+}
+
+function comparePassword(password, hash) {
+  const bcrypt = require("bcryptjs");
+  return bcrypt.compareSync(password, hash);
+}
+
+module.exports = {
+  authenticateToken,
+  generateToken,
+  hashPassword,
+  comparePassword,
+  JWT_SECRET
+};
diff --git a/src/routes/auth.js b/src/routes/auth.js
new file mode 100644
index 0000000..7c8d9e0
--- /dev/null
+++ b/src/routes/auth.js
@@ -0,0 +1,78 @@
+const express = require("express");
+const router = express.Router();
+const db = require("../models/db");
+const { generateToken, hashPassword, comparePassword } = require("../middleware/auth");
+
+// POST /api/auth/register
+router.post("/register", (req, res) => {
+  const { username, password, email } = req.body;
+
+  if (!username || !password) {
+    return res.status(400).json({ error: "Username and password are required" });
+  }
+
+  if (password.length < 6) {
+    return res.status(400).json({ error: "Password must be at least 6 characters" });
+  }
+
+  try {
+    const existing = db.prepare("SELECT id FROM users WHERE username = ?").get(username);
+    if (existing) {
+      return res.status(409).json({ error: "Username already exists" });
+    }
+
+    const hashedPassword = hashPassword(password);
+    const result = db.prepare(
+      "INSERT INTO users (username, password, email) VALUES (?, ?, ?)"
+    ).run(username, hashedPassword, email || null);
+
+    const user = { id: result.lastInsertRowid, username };
+    const token = generateToken(user);
+
+    res.status(201).json({ user: { id: user.id, username }, token });
+  } catch (err) {
+    res.status(500).json({ error: "Registration failed" });
+  }
+});
+
+// POST /api/auth/login
+router.post("/login", (req, res) => {
+  const { username, password } = req.body;
+
+  if (!username || !password) {
+    return res.status(400).json({ error: "Username and password are required" });
+  }
+
+  try {
+    const user = db.prepare("SELECT * FROM users WHERE username = ?").get(username);
+
+    if (!user) {
+      return res.status(401).json({ error: "Invalid credentials" });
+    }
+
+    if (!comparePassword(password, user.password)) {
+      return res.status(401).json({ error: "Invalid credentials" });
+    }
+
+    const token = generateToken({ id: user.id, username: user.username });
+    res.json({ user: { id: user.id, username: user.username }, token });
+  } catch (err) {
+    res.status(500).json({ error: "Login failed" });
+  }
+});
+
+// GET /api/auth/me - Get current user
+router.get("/me", (req, res) => {
+  if (!req.user) {
+    return res.status(401).json({ error: "Not authenticated" });
+  }
+
+  const user = db.prepare("SELECT id, username, email, created_at FROM users WHERE id = ?").get(req.user.id);
+  if (!user) {
+    return res.status(404).json({ error: "User not found" });
+  }
+
+  res.json({ user });
+});
+
+module.exports = router;
diff --git a/src/index.js b/src/index.js
index 4d5e6f7..9a0b1c2 100644
--- a/src/index.js
+++ b/src/index.js
@@ -2,6 +2,8 @@ const express = require("express");
 const cors = require("cors");
 const taskRoutes = require("./routes/tasks");
 const projectRoutes = require("./routes/projects");
+const authRoutes = require("./routes/auth");
+const { authenticateToken } = require("./middleware/auth");
 const { errorHandler } = require("./middleware/errorHandler");

 const app = express();
@@ -12,8 +14,10 @@ app.use(express.json());

 app.get("/health", (req, res) => res.json({ status: "ok" }));

-app.use("/api/tasks", taskRoutes);
-app.use("/api/projects", projectRoutes);
+app.use("/api/auth", authRoutes);
+
+app.use("/api/tasks", authenticateToken, taskRoutes);
+app.use("/api/projects", authenticateToken, projectRoutes);

 app.use(errorHandler);
'''

# Write evidence files
stat_path = os.path.join(evidence_dir, f"{job_id}_stat.txt")
patch_path = os.path.join(evidence_dir, f"{job_id}_patch.txt")
with open(stat_path, "w") as f:
    f.write(diff_stat)
with open(patch_path, "w") as f:
    f.write(diff_patch)

# 4. Create Evidence records
stat_evidence_id = str(uuid.uuid4())
patch_evidence_id = str(uuid.uuid4())

c.execute(
    """INSERT INTO evidence (id, ticket_id, job_id, kind, command, exit_code, stdout_path, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
    (
        stat_evidence_id,
        TICKET_ID,
        job_id,
        "git_diff_stat",
        "git diff --stat",
        0,
        os.path.abspath(stat_path),
        now,
    ),
)

c.execute(
    """INSERT INTO evidence (id, ticket_id, job_id, kind, command, exit_code, stdout_path, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
    (
        patch_evidence_id,
        TICKET_ID,
        job_id,
        "git_diff_patch",
        "git diff",
        0,
        os.path.abspath(patch_path),
        now,
    ),
)

# 5. Create Revision record
revision_id = str(uuid.uuid4())
c.execute(
    """INSERT INTO revisions (id, ticket_id, job_id, number, status, diff_stat_evidence_id, diff_patch_evidence_id, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
    (
        revision_id,
        TICKET_ID,
        job_id,
        1,
        "open",
        stat_evidence_id,
        patch_evidence_id,
        now,
    ),
)

conn.commit()
conn.close()

print(f"Ticket: {TICKET_ID}")
print(f"Job: {job_id}")
print(f"Revision: {revision_id}")
print(f"Evidence stat: {stat_evidence_id}")
print(f"Evidence patch: {patch_evidence_id}")
print("Done - ticket is now in needs_human with a revision")
