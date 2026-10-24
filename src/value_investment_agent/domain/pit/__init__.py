"""Point-in-time contracts: when a reported fact may be treated as known.

This subpackage is deliberately the narrowest possible layer. It answers exactly
one question — "as of date D, was report period P available to an honest
observer?" — and nothing else. It never scores, never values, never sizes.

Every rule here is conservative: it may delay a fact, never advance one. A rule
that can only delay cannot manufacture look-ahead, which is the single property
the rest of the system depends on.
"""
