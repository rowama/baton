---
id: user.long-running-work
title: Long-running work and coming back
audience: owner
order: 70
summary: Work can run after your chat ends; what happens when you come back, or move to another computer.
related: [user.check-on-your-work, user.when-something-is-wrong]
---

## Here, now {#here-now}

Work keeps going when you are not looking. A helper can take minutes or hours, and your assistant may stop its turn before the work finishes. When you return, ask "where are we?"

If your assistant cannot be woken when work finishes, it tells you **before** it starts, in plain words, that it might not notice when the work finishes and roughly how long that may take. Then you know when to check back.

## Coming back later {#coming-back}

Everything about the work is in your project, so a new conversation can pick up where the last one ended. Open your assistant in the project and ask where things stand. It reads the record and carries on.

## Moving to another computer {#another-computer}

1. Get the project there (`git clone`, or pull).
2. Set up that computer's helpers and accounts: accounts and keys never travel with the project. See [connecting an account](user.connect-an-account#here-now).
3. Ask your assistant to carry on, or run these yourself:

```baton
baton doctor
baton resume <run>
```

`resume` checks the record is intact, catches up on work that was running, and takes over the work.

## Only one assistant at a time {#one-at-a-time}

A piece of work is changed by one assistant at a time. If another has it, you are told who, and until when. Taking it over needs your approval, because the other assistant may still be working.
