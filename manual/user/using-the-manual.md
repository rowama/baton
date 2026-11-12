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

The page is always at `http://127.0.0.1:47474/`, so you can bookmark it. It stays up until you close it (Ctrl-C in the terminal, or **Quit** on the page); `baton ui --detach` runs it in the background the same way. Running `baton ui` again closes the old page and starts the current version, so it is the way to pick up an update. Give `--idle-timeout SECONDS` to have it close itself when unused; a later launch can only lengthen a running page's timeout, never shorten it, and tells you when yours was not applied. When your assistant starts the page it always sets a timeout. If another program already uses that port, choose a different one with `--port`.

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
