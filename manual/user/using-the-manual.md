---
id: user.using-the-manual
title: Using this manual
audience: owner
order: 5
summary: Open the manual from the setup page, search it, read it in the terminal, or ask your assistant.
related: [user.getting-started]
---

## Here, now {#here-now}

- **On the setup page:** a **?** beside a part of the page opens the short answer for it. **Open the full guide** goes to the whole page. The **Manual** tab holds everything, with a contents list and search. Press `/` to search from anywhere.
- **In the terminal:** `baton help` lists every topic; `baton help <topic>` prints one.
- **Through your assistant:** ask "how do I...?"; it answers from the manual.

Open the page with:

```baton
baton ui
```

## Reading in the terminal {#terminal}

```baton
baton help
baton help user.connect-an-account
baton help user.connect-an-account#key-refused
baton help --search keyring
```

A topic's name is its part and its title: `user.` for the user guide, `admin.` for the admin guide, `providers.` for a provider's page. Adding `#` and a heading's name prints just that section. Every command also ends its `--help` with the topic that explains it.

## How each topic is laid out {#layout}

Every topic opens with **Here, now**: the short answer for the place you are. Read on for the detail. If you only need to get unstuck, that first box is usually enough.
