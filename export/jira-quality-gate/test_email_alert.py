"""
Temporary test script — verifies email alerts are working.
Will be deleted after test is confirmed.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import post_error

post_error("Test alert from TaxOps automation — email notifications are working correctly. You can ignore this message.")
print("[TEST] post_error() called — check thenriquez@rippling.com and rannabi@rippling.com for the alert email.")
