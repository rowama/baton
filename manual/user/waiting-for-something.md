---
id: user.waiting-for-something
title: Work that waits for something
audience: owner
order: 75
summary: Some parts wait days for something outside the work to happen; nothing runs meanwhile, and every wait ends with your decision.
related: [user.long-running-work, user.check-on-your-work, admin.scheduling-checks]
---

## Here, now {#here-now}

Some work has to pause until something outside it happens: a price reaches a level, a signed contract comes back, enough survey answers arrive. A part like that is **waiting**. A small check looks at what it waits for, and the part goes on as soon as the check finds it has happened.

Nothing keeps running while a part waits. Closing your assistant, shutting the lid or restarting your computer changes nothing: the wait is part of the record, like a question waiting for your answer.

## Where it stands {#where-it-stands}

Ask your assistant where things stand. For each waiting part it tells you what it waits for, since when, until when, and when it was last checked. You can check it yourself:

```baton
baton waits check
```

That looks once at every waiting part and stops. One that is met is taken in now and the work goes on. The others keep waiting.

## Who checks, and how often {#who-checks}

Your assistant checks whenever it picks the work up again. Between conversations, nothing checks unless you ask this computer to. Your assistant offers that once, and shows you exactly what it would add (an entry in cron, or in Windows Task Scheduler) and how often it would run. It adds it only if you say yes. Without it, waits still end: they are just noticed later, the next time someone checks. See [scheduling the check](admin.scheduling-checks#here-now).

## When a wait runs out {#when-it-runs-out}

Every wait has a limit, so nothing waits forever and nothing is dropped without you knowing. The process sets the limit, and your project caps it (30 days unless changed). When a wait runs out, your assistant asks you what to do:

| You see | What happens |
|---|---|
| Keep waiting | The check runs again now, and the part waits for another period |
| Go on without it | The part is skipped and the work goes on (offered only where the process allows it) |
| Stop waiting and set this aside | The part stops here; the rest of the work may not be able to finish without it |

If the check itself keeps failing (the site it looks at is down, say), you are told after three failures in a row, with what went wrong, so a broken check never looks like nothing has happened yet.
