---
id: 2026-11-browser-automation
title: "Steps can operate a web app in a browser for the owner, with the owner's authorization"
status: proposed            # ON HOLD: after 2026-11-step-tool-harness
level: major
decisions: []
touches: [design/recipes.md, design/workers.md, design/platform-and-security.md, design/director-interface.md, design/versioning.md]
---

# Steps can operate a web app in a browser for the owner, with the owner's authorization

> **On hold.** Discussed 2026-11-06. It builds on the step tool loop in [2026-11-step-tool-harness](2026-11-step-tool-harness.md).

## Request

### Problem

Some processes run through a web app the owner already uses: entering a business's inputs into an account, or collecting its outputs. Plain HTTP fetching cannot handle logins, forms or pages built by JavaScript. A step should be able to do this work for the owner in a real browser, so the process runs smoothly while the owner stays in control of the account.

This is a different risk class from reading the web:

- it needs the owner's credentials;
- page content can try to instruct the model;
- clicks and submits have real effects.

### Acceptance criteria (draft)

1. A new capability `browser` (a new capability vocabulary version, §5.6) is provided by Baton through a headless browser. Playwright for Python is pip-installable with a downloadable Chromium ([Playwright: getting started](https://playwright.dev/python/docs/library)). A harness's own browser tools may also qualify.
2. A step may use the browser only on sites the owner has authorized for that recipe. Each authorization is recorded and revocable.
3. Credentials come only through Baton's `secret:` references. They are never in a prompt, an artifact or a log.
4. Any action that changes state on the site (submit, purchase, send, delete) stops at a human gate showing what will be done, unless the owner has approved that exact action type for that site beforehand.
5. The step keeps a record for the owner: pages visited, actions taken and screenshots as artifacts.
6. Page content is untrusted data. Instructions found in a page are never followed, and a page asking for credentials or approval escalates to the owner.
7. When authorizing a site, the Director tells the owner that the site's terms may restrict automated use, and that this is the owner's decision.

### Open questions

- Is the browser a Baton runner tool, a separate adapter, or both?
- Is the session kept between runs (stay logged in), or a fresh login each time?
- Should CAPTCHAs and two-factor prompts always escalate to the owner? (Suggest yes; Baton never tries to bypass them.)

## Design

To be written when taken off hold.

## Plan

## Log
