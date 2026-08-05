Auth-Gated App Testing Playbook

Step 1: Create Test User & Session (mongosh)
use('test_database');
var userId = 'test-user-' + Date.now();
var sessionToken = 'test_session_' + Date.now();
db.users.insertOne({ user_id: userId, email: 'test.user.'+Date.now()+'@example.com', name: 'Test User', picture: 'https://via.placeholder.com/150', created_at: new Date() });
db.user_sessions.insertOne({ user_id: userId, session_token: sessionToken, expires_at: new Date(Date.now()+7*24*60*60*1000), created_at: new Date() });

Step 2: Test Backend API with Authorization: Bearer <session_token> OR cookie session_token.

Step 3: Browser test - set cookie session_token (httpOnly, secure, sameSite None) then navigate.

Checklist:
- users doc has user_id (UUID), _id excluded in queries
- user_sessions.user_id matches users.user_id
- /api/auth/me returns user (not 401)
- Dashboard loads without redirect
