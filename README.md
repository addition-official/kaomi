# Kaomi

A Windows-style emoji picker and clipboard history for KDE Plasma 6.

Press **Meta+.** and a panel opens at your text cursor: emoji, kaomoji and
symbols, searchable, with skin tones. Pick one and it is typed into the app
you were in, at the cursor, keeping the formatting there (a large font size in
Gmail stays large), and without touching your clipboard. Press **Meta+V** for
a clipboard history that works like the Windows one: click an item to paste
it, pin the ones you want to keep, delete the ones you don't, and Clear all
really clears everything.

One Python file. `python3 kaomi.py --setup` installs it.

## Requirements

- Kubuntu 26.04 (or anything with Plasma 6 and the usual KDE packages)
- Plasma 6 on Wayland. Typing emoji needs Plasma 6.6 or newer; on older
  Plasma they are pasted instead (same place, but the app's formatting may
  not carry over)
- Plasma's own clipboard widget (Klipper) left enabled in the system tray;
  Kaomi works with it, not instead of it

Setup installs what it needs with apt and asks for your password for that.

## Install

```
python3 kaomi.py --setup
```

Run it as your normal user. It asks one question (whether to take over
Meta+V from Plasma's clipboard), then installs packages, builds two small
helpers, sets up the shortcuts, and starts Kaomi in the background. Re-run the
same command any time to update; it only changes what needs changing.

The first time Kaomi starts, KDE asks whether it may "control input devices".
Click Allow: that is how it pastes clipboard items for you. You'll see a short
"Remote control session started" notice once per login after that. Emoji don't
need this permission; they are typed by Kaomi's KWin plugin.

If setup says to log out and back in, do that once. It is needed when a
shortcut couldn't be applied live, or when the KWin plugin was updated
(KWin can't swap a plugin it has already loaded).

## Using it

| Key | What it does |
|---|---|
| Meta+. | Open or close the emoji panel |
| Meta+V | Open or close the clipboard history |
| Type | Search emoji |
| Arrows, Enter | Choose and insert |
| Escape | Close |
| Click outside the panel | Close |

While the panel is open, Escape belongs to it: it always closes the panel in
one press (even from Settings or with a search typed), and no app sees that
key, wherever the keyboard focus is. Escape with Ctrl, Alt, Meta or Shift, and
Escape in KDE's own screens (Overview, moving a window), work as usual. Clicks
outside the panel are noticed the same way, even in the app that has focus.

Clipboard tab: click an item to paste it. **Shift+Enter** (or the "…" button,
then "Paste as text") pastes without formatting. **Delete** removes an item
for good. **Ctrl+P** pins or unpins. Pinned items survive logout; the rest of
the history (up to 200 items, images capped at 200 MB in total) is kept in
memory only. Passwords (anything a password manager marks as secret) are
never recorded.

Settings (the gear in the panel): close after inserting or stay open, which
keys are used to paste clipboard items (Shift+Insert works in terminals,
Ctrl+V elsewhere), where the panel opens, and whether clipboard history is on.

With "stay open" on, you can click several emoji in a row, as fast as you
like; they are typed in order into your app while it keeps keyboard focus (no
flicker), and any click outside the panel still closes it. If you switch to
another app before a pick has gone in, that pick is dropped rather than typed
into the wrong app.

Recently used shows the last 3 rows of emoji you picked.

## What setup changes on your system

Everything is undone by `kaomi --uninstall`.

- Packages: PyQt6, the Noto Color Emoji font, wl-clipboard and its build
  dependencies, AT-SPI, and the KWin development headers.
- `~/.local/bin/kaomi`, a menu entry, and an autostart entry so Kaomi runs in
  the background from login.
- Shortcuts: Meta+. goes to Kaomi (Plasma's own emoji selector is moved to
  Meta+Ctrl+Alt+Shift+Space). With Meta+V taken over, Plasma's clipboard popup
  shortcut is cleared. The old bindings are remembered and put back on
  uninstall.
- Klipper's "Prevent empty clipboard" option is turned off. With it on,
  Plasma puts its own last item straight back whenever the clipboard is
  emptied, which would undo Clear all and Delete. Restored on uninstall.
- A small KWin plugin (`kaomi_caret.so`) is built and installed as a
  root-owned system file, because that is where KWin loads plugins from. It
  is enabled for your session only. It:
  - tells Kaomi where the text cursor is and when you click outside its panel;
  - types emoji into your app. Apps with an input-method connection (Chrome,
    kitty and most modern apps) get the text the way an on-screen keyboard
    sends it, which works for every emoji and keeps the formatting. Other
    apps get key presses sent straight to them, with exactly the modifiers
    each character needs, so Caps Lock or a key you're holding can't change
    what comes out;
  - takes the Escape key while the panel is open;
  - in stay-open mode, takes clicks on the panel itself so your app never
    loses keyboard focus (some apps, Gmail for one, lose their cursor
    position otherwise).

  Only the running Kaomi can use it: the first program to register gets the
  role until it quits, and no other program can take it over meanwhile. It
  never types while the screen is locked. Apart from the above, it only
  watches and never changes or blocks any input.
- Two helpers built into `~/.local/opt/kaomi/`: wl-clipboard 2.3 (Ubuntu's
  is too old for Plasma 6's clipboard protocol) and `kaomi-copy`, which puts
  the clipboard back with all its formats (used by clipboard history, and by
  emoji inserts on Plasma older than 6.6, where they are pasted instead of
  typed).

Downloads made during setup are pinned to exact versions and checked, since
these tools see everything you copy.

## After a Plasma update

KWin refuses a plugin built for a different version, so after Plasma updates
Kaomi shows a notification with an "Update now" button. Click it, type your
password, log out and back in. Until then the panel opens at the mouse
instead of the text cursor, emoji are pasted instead of typed, and stay-open
mode falls back to a mode where focus briefly hops to your app for each
paste. You can check the state any time with `kaomi --kplug-status`
(`active`, `outdated`, or `off`).

## Uninstall

```
kaomi --uninstall
```

Removes the app, shortcuts, plugin and helpers, and restores the Plasma
settings it changed. It asks whether to also delete your settings and pinned
items.

## Troubleshooting

`~/.cache/kaomi.log` says what happened on every open, close, pick, paste,
and clipboard change. Start there. It trims itself to its newest part once it
passes 512 KB.

- An emoji didn't go in: look at the `pick` line for it. It says whether the
  emoji was typed, pasted, or only copied. A `typing: nothing typed` line
  right after says why (for example, you switched apps first).
- Clipboard items don't paste: check the log for `auto-insert`. If you
  declined KDE's permission prompt, Settings has "Ask KDE for input permission
  again".
- Clipboard history empty and stays empty: the log will say if wl-paste
  couldn't watch the clipboard. Re-run setup.
- Panel opens at the mouse instead of the text cursor: the KWin plugin isn't
  loaded (see "After a Plasma update"). Apps that don't use Wayland text input
  fall back to the mouse position too.
- Setup says the plugin couldn't be built: the full log is in
  `~/.local/opt/kaomi/kwin-plugin/last-build.log`. Usually the KWin
  development package doesn't match the installed KWin yet; run
  `sudo apt update && sudo apt upgrade` and try again.

## Known limitations

- In apps that get key presses, a character that isn't on your keyboard
  layout is sent on the F24 key with a one-off keyboard layout for that app
  only, then your layout is sent back. KWin's own keyboard state and your
  other apps aren't affected.
- If no text field has focus, the app gets key presses: a kaomoji with letters
  in it can trigger a site's single-key shortcuts (YouTube's "f" for
  fullscreen, say).
- Emoji can't be typed into Chrome's password fields; Chrome blocks that.
- Picks longer than 256 characters (none of the built-in ones) are pasted
  instead of typed.
- If you close the panel, scroll or move the window without typing anything,
  and reopen, it may open at the old cursor position. Typing one character
  fixes it: Chrome and friends only re-announce the cursor when it moves.
- Kaomi trusts everything running as your user, like any desktop app. Any
  program on your session bus can ask the panel to close, and the KDE input
  permission token in `~/.local/share/kaomi/` is what lets Kaomi press paste
  keys in your apps; treat that file like a credential on a shared machine.

## Credits

The emoji list built into `kaomi.py` comes from:

- [Unicode](https://www.unicode.org/)'s emoji data (names, groups and order),
  via [unicode-emoji-json](https://github.com/muan/unicode-emoji-json) by
  Mu-An Chiou (MIT License)
- [emojilib](https://github.com/muan/emojilib) by Mu-An Chiou (search
  keywords, MIT License)

Their full license notices are in `kaomi.py`, just above the emoji data. The
emoji themselves are drawn with Google's Noto Color Emoji font, installed from
Ubuntu's own package.

## A note on how this was built

The idea, the requirements, and the calls about how it should behave are
mine: a panel that works the way the Windows one does, a clipboard history
where Delete and Clear all actually mean it, and no focus flicker. I tested it
on my own machine, one bug at a time; the fixes were also checked with
automated tests in a copy of Kubuntu 26.04 running the real KWin.

I used AI assistance to build and rework much of the code, to find and fix the
bugs I reported back, and to write this README. Where a piece of KDE
behaviour had to be understood before it could be worked around (Klipper's
refill of an emptied clipboard, KWin plugin loading, Wayland's rule that only
the focused window may write the clipboard), the digging and the fix were done
together; the direction and the final say were mine.
