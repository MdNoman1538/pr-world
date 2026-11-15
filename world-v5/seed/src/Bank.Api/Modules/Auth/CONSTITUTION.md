# Auth — constitution
**Purpose:** Who is calling and what they may do.
**Owner:** Security · **Risk:** HIGH
**Rules:** Every endpoint has an [Authorize] policy. Staff roles: teller, loan-officer, compliance-officer, admin. User ids come only from ICurrentUser.
**Forbidden:** AllowAnonymous on any endpoint that touches customer data or money; reading a user id from a request body.
