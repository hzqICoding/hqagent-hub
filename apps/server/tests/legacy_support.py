"""Frozen R1 admission policy for historical regression fixtures, never production.

D48 forbids *new* R1 HTTP writes. Existing tests retain their original assertions
against the old policy that created historical records; R1.5 HTTP uses the real
create_app without these test-scoped substitutions.
"""
from server.app import ROUTES
from server.service import Service

LEGACY_ROUTES = []
for method, path, op, im, om, status in ROUTES:
    if method == 'PATCH' and op == 'update_conversation':
        continue
    if op == 'create_conversation':
        om, status = 'RemoteConversationView', 201
    if op == 'messages':
        om = 'RemoteMessagePage'
    LEGACY_ROUTES.append((method, path, op, im, om, status))


class HistoricalService(Service):
    browser_get = Service.get

    def messages(self, tx, owner, identifier, before, limit):
        return self.page(tx, owner, 'message', before, limit, identifier)

    def conversations(self, tx, owner, cursor, limit, worker=None, workspace=None):
        return self.page(tx, owner, 'conversation', cursor, limit)
