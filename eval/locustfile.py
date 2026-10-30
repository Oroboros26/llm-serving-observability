"""Load test. Run: locust -f eval/locustfile.py --host http://localhost:8000 -u 50 -r 10 -t 2m --headless
Repeated prompts exercise the cache; set UNIQUE=1 to force misses (cold path)."""
import itertools
import os
import random

from locust import HttpUser, between, task

KEY = os.getenv("LOAD_API_KEY", "sk-local-a")
POOL = [f"What is {a} plus {b}?" for a in range(1, 11) for b in range(1, 11)]
_counter = itertools.count()


class Client(HttpUser):
    wait_time = between(0.1, 0.5)

    @task
    def ask(self):
        prompt = f"Give me fact number {next(_counter)}" if os.getenv("UNIQUE") else random.choice(POOL)
        self.client.post("/v1/chat/completions",
                         json={"messages": [{"role": "user", "content": prompt}], "max_tokens": 64},
                         headers={"Authorization": f"Bearer {KEY}"})
