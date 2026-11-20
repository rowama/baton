---
id: user.answer-questions-and-decide
title: Answer questions and decide
audience: owner
order: 50
summary: What you are asked, what each choice does, and how nothing is recorded until you confirm.
related: [user.what-is-baton, user.how-you-want-to-be-told, user.check-on-your-work]
---

## Here, now {#here-now}

When work needs you, your assistant asks in plain words. Answer in your own words. It then says back what it understood, and records it only when you confirm. You can take as long as you like: the work waits.

A question usually comes with the reason it matters and a best guess, so often all you need to say is "yes" or "not quite, because...".

## The choices you may be offered {#the-choices}

The wording changes with the situation. These are the choices, and what each does:

| You see | What happens |
|---|---|
| **Looks right** | The result is accepted and the work carries on with the next part. |
| **Not yet: here's what to change** | That part is redone, with what you said as guidance. |
| **Yes, that's the right size** / **No, it's bigger or smaller than that** | The work goes ahead at that size, or the sizing is redone with what you said. |
| **Yes, look at that again** / **Keep it as it is** | When the work suggests one of its ratings is wrong: that rating is redone (you approve the result), or it stays. |
| **Include these** / **That's not quite it** | Each piece you choose is started, or the breakdown of your goal is redone. |
| **That's an accurate picture** | The summary of your existing work is accepted as the starting point. |
| **Try again** / **Try again with your answers** | A part that stopped is tried again, with what you said. |
| **Set this aside for now** | That part stops. The rest of the work may not be able to finish without it. |
| **Give it another round** / **Stop working on this piece** | For a repeated piece of work that has not settled: allow another set of tries, or stop it. |
| **Keep that change** / **Undo that change** | A change to files the process protects stays, or is undone and redone. |
| **Keep the change** | Files you approved earlier were changed outside the work (by hand, say): the change stays and becomes what you approved. Otherwise, put the files back as they were, and the work carries on. See [files you approved](#approved-files). |
| **Replace the existing file** / **Keep the existing file** / **Save the new one alongside** | What to do when the work wants to write a file that already exists. |
| **Leave it as it is** / **Use my edited version** | After you edited a file Baton delivered: keep your edit as it is, or let later work build on it. |

## Files you approved stay as you approved them {#approved-files}

Some approvals also lock files: when you approve a set of acceptance specs, say, later parts of the work may not change them on their own. If a part changes one, you are asked (**Keep that change** / **Undo that change**), or, where the process says so, that part is simply redone. If someone changes one by hand between parts, the next part waits until you keep the change or the file is put back. Redoing the part you approved releases the lock; your next approval locks the files again.

## Confirming before anything is recorded {#confirm-back}

Nothing from the conversation is recorded until you confirm what was understood. Your assistant restates it ("So: one machine per site to start, and you will handle the permits yourself?") and records it only after you say yes, together with your own words. If the restatement is wrong, say so; nothing was recorded. Asking your assistant to do something ("set up the recipe builder and run it") is not a confirmation either: it first tells you what it will set up or record, and records your yes, not the request.

What you answer stays answered for the rest of that piece of work. If a part is done again, for example after a check sends it back, it is given your answers, and so is the check, so you are not asked the same thing twice; you are asked again only about something your answers leave open. When you accept what a helper suggested, the suggestions themselves are kept with your answer.

You may answer only some of a set of questions. Your assistant will tell you what is still needed before the work can go on.

## Answering in a file {#answer-file}

Some things are easier to fill in than to talk through, such as matching twenty receipt lines to twenty items. Ask your assistant for an answer file. It is a plain text file with every question or field in it, a short note on each, and the best guess already filled in where there is one. Fill it in with any text editor, and add any files the work asks for (a photo, a signed page) by writing where they are on your computer. Then tell your assistant it is done. It checks what you wrote and tells you what will be recorded; nothing is recorded until then. If something does not fit (a choice that is not offered, a needed answer left empty), it says what, and you can fix the file.

If you do a part of the work yourself, it can be answered the same way: what it asks for becomes the fields of the file. You can also do it in conversation: for a table, such as receipt lines, your assistant goes through it with you one row at a time, then reads the whole set back before recording it.

## Answering on a page {#answer-on-a-page}

For a long form, a table or something to look at, your assistant may give you a link instead. It opens a page on your own computer, in your browser, showing the question, what to look at, and the choices or fields to fill in. The page checks what you filled in and says plainly what is missing. Then it shows what will be recorded, with a box for anything you want to add, and records it only when you press **Confirm**. You do not need your assistant to be part of this: it sees your answer the next time it looks.

If the work needs a file from you (a photo, a signed page), the page has a button to choose it from your computer; it is sent when you press **Confirm**, kept only until your answer is recorded, and then becomes part of the work. A file can be up to 100 MB. Pictures the work shows you appear on the page; other documents can be opened or downloaded.

Each project has its own address on the page, such as `http://127.0.0.1:47474/p/garden-shed/requests`, which lists everything waiting for you in that project, newest first, and updates itself while you have it open. The address stays the same for as long as the project exists, so you can bookmark it. Its name is the project's name, which starts as the project folder's name; to change it, tell your assistant. To see a project's page yourself, run this in the project's folder:

```baton
baton ui
```

If the page cannot show a question, it says so and shows how to answer it with an answer file instead. Closing the page loses nothing: the question waits until you answer it.

## If a question changed before you answered {#changed}

While you think, the work can move on: another part may add a reason to a question, or a part that was tried again may come back with new questions. Your answer always goes to the question as you saw it. If that question has changed since, nothing is recorded; your assistant shows you the question as it is now, and you answer that one. On the page, you are told the question changed, with a link to what is waiting now.

## Sizing the work {#sizing}

Early on, the work is sized, so that it gets as much care as it needs and no more. Some processes give one size (small, standard, large). Others rate the work on a few separate things, such as how much is still unknown and how carefully the result must be checked, each with the reason for the rating. You are shown all of them together and asked once whether they are right. If one is off, say which and why; the sizing is redone with your words.

A small piece of work goes ahead without asking you, unless the process always asks about one of the ratings, for example how carefully the work must be checked.

Your project's rules can set a lowest rating, for example "software work here is always checked at least moderately carefully". When the sizing comes out lower, the rating is raised to that rule, and your assistant says which ratings your rules raised before you approve. A raised rating always waits for your approval. Work that started before a rule changed keeps the rules it started with, until it is sized again.

The sizing can change later. If you see the work is bigger or smaller than it was rated, tell your assistant; the sizing is redone and you approve the new one. It changes only the parts not yet started. Sometimes the work itself finds that a rating looks wrong (for example, a change turns out to touch other people's data). Your assistant then tells you why and asks: **Yes, look at that again** redoes that rating, and you approve the result; **Keep it as it is** leaves it. Nothing waits on your answer in the meantime.

## Confirming a document {#documents}

Some work builds on a document your project already has. Before that work starts, your assistant tells you which document it proposes and asks you to confirm. If the document was changed after it was approved, the assistant says so: confirming then means the work uses it as it is now. If nothing fits, say so; you can point to a file you consider settled, and for a document that is only nice to have, the work can go on without one.

To make a file of your own available this way, tell your assistant it is settled. It records that you vouch for the file, with your words. If you change the file later, tell your assistant again, and the new version is recorded too.

If a document changes after work started using it, you decide whether to switch. Switching means the parts that already used the old version are done again with the new one; your assistant tells you that before you decide. Other pieces of work that use the same document are not affected.

## Confirming a change to the rules {#rules}

Your project has a few rules every piece of work follows: the lowest sizing work may get (see [sizing the work](#sizing)), what may be pushed or released without asking you (see [what Baton may do](user.what-baton-may-do#changing)), and which process suits a kind of work. When you ask for work of a kind the rules name, your assistant proposes that process and says the rules name it; you can still choose another. To change a rule, tell your assistant; it confirms the change with you and records it with your words. If someone edits the rules by hand, your assistant tells you what changed and asks whether to accept it. Until you say yes, the rules you last confirmed still apply. A project that had rules before they were recorded is asked about once, the same way.

## Parts of the work for a person {#person-steps}

Some work has parts only a person can do: a site visit, examples only you have, the final look before you approve. The first time you start such work in a project, your assistant asks whether you will do those parts yourself. Yes is the answer it expects, since you started the work. If someone else will, give their name: Baton sets them up, and those parts go to them. Your answer is kept for the project, so you are not asked again; tell your assistant if it changes. Whoever does those parts, every decision is still yours.

## If a question confuses you {#confusing}

Say so. A question you do not understand is a problem with the question, not with you. Ask what it means, or say what you think it is getting at, and your assistant will put it differently.
