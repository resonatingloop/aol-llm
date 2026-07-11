from aol_llm.config import database_path; import sqlite3; p=database_path(); con=sqlite3.connect(p); rows=con.execute(\"select b.display_name,
  r.status, r.error, r.output_tokens, r.created_at from memory_distill_runs r join buddies b on b.id = r.buddy_id order by r.created_at desc limit
  10\").fetchall(); print('db:', p); [print(r) for r in rows]
