"""테스트 전역 fixture — rate-limit 격리.

기본적으로 limiter 를 비활성화. test_rate_limit.py 만 fixture 에서 다시 활성화.
"""
from __future__ import annotations
import os

# pytest 가 어떤 test module 을 먼저 import 해도 limiter 가 꺼진 상태로 기동.
os.environ.setdefault("TUBEWAR_RATE_LIMIT_DISABLE", "1")
