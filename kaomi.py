#!/usr/bin/env python3
"""
Kaomi: a Windows-style emoji picker and clipboard history for KDE Plasma.

Install / update:  python3 kaomi.py --setup
Remove:            kaomi --uninstall
Run with no arguments to open/close the picker (bind this to Meta+.).
Run with --clipboard to open it on the clipboard history tab.
Run with --daemon to start it hidden in the background (used at login).

Picking an emoji types it into the app you were typing in: Kaomi's KWin plugin
presses it as a real keystroke (Plasma 6.6+), so it lands at the cursor with the
formatting there and never touches the clipboard. Without that it is lent to the
clipboard instead (marked secret so clipboard history ignores it), pasted with
Shift+Insert through KDE's remote-input permission, and your old clipboard is
put back with all its formats (a small helper, kaomi-copy, is built for that).

Clipboard history is kept in memory only; pinned items are saved to
~/.local/share/kaomi/pinned/. Delete and Clear all also wipe Plasma's own
clipboard history (Klipper), and setup turns off Klipper's "Prevent empty
clipboard" so deleted items can't be put back on the clipboard.
"""
import os, sys, socket

APP_ID = "kaomi"
VERSION = "1.0"
if "--version" in sys.argv:
    print(f"{APP_ID} version {VERSION}"); sys.exit(0)

# ---------------------------------------------------------------- setup ----
# "python3 kaomi.py --setup" installs or updates everything.
# (Handled before any Qt import, since Qt may not be installed yet.)
SETUP_SH = '#!/usr/bin/env bash\n# Installs (or updates) Kaomi, the Windows-style emoji picker + clipboard history for KDE Plasma.\n# Run:  python3 kaomi.py --setup\n# Safe to run again any time: it just updates everything and restarts the app.\n# Remove everything again with:  kaomi --uninstall\nset -e\nAPP=kaomi\nOLD=win-emoji-picker      # the name before 1.0\nBIN="$HOME/.local/bin/$APP"\nCONF_DIR="$HOME/.config/$APP"\n\nif [ "$(id -u)" -eq 0 ]; then\n  echo "Run setup as your normal user (without sudo). It asks for your password when needed."\n  exit 1\nfi\n\nSRC="${KAOMI_SRC:?}"     # the file you ran --setup from\necho "==> Setting up Kaomi version $(grep -m1 \'^VERSION\' "$SRC" | cut -d\'"\' -f2)"\n\n# Kaomi used to be called "win-emoji-picker": stop the old one, keep your\n# settings, pins and the built clipboard tool, and remove the old files.\nif [ -e "$HOME/.local/bin/$OLD" ] || [ -d "$HOME/.config/$OLD" ] || [ -d "$HOME/.local/share/$OLD" ]; then\n  echo "==> Moving over from $OLD (the old name)"\n  timeout 3 "$HOME/.local/bin/$OLD" --quit 2>/dev/null || true\n  sleep 0.5\n  pkill -u "$(id -u)" -f -x "[^ ]*python3[^ ]* $HOME/.local/bin/$OLD( --daemon| --clipboard)?" 2>/dev/null || true\n  pkill -u "$(id -u)" -f "$OLD-caret-helper" 2>/dev/null || true\n  for Q in qdbus6 qdbus; do\n    command -v $Q >/dev/null && { $Q org.kde.KWin /Scripting org.kde.kwin.Scripting.unloadScript \\\n        "$OLD-helper" >/dev/null 2>&1 || true; break; }\n  done\n  for d in .config .local/share .local/opt; do\n    if [ -d "$HOME/$d/$OLD" ] && [ ! -e "$HOME/$d/$APP" ]; then\n      mv "$HOME/$d/$OLD" "$HOME/$d/$APP"\n    elif [ -d "$HOME/$d/$OLD" ]; then\n      mv "$HOME/$d/$OLD" "$HOME/$d/$OLD.old-copy"      # already have the new one: keep aside\n    fi\n  done\n  # tied to the old name: KDE asks for the input permission once more\n  rm -f "$HOME/.local/share/$APP/portal-token" "$HOME/.local/share/$APP/kwin-helper.js"\n  rm -f "$HOME/.local/bin/$OLD" "$HOME/.local/share/applications/$OLD.desktop" \\\n        "$HOME/.local/share/applications/$OLD-clipboard.desktop" "$HOME/.config/autostart/$OLD-daemon.desktop" \\\n        "$HOME/.local/share/icons/hicolor/scalable/apps/$OLD.svg" \\\n        "$HOME/.local/share/icons/hicolor/scalable/apps/$OLD-clipboard.svg" "$HOME/.cache/$OLD".*log*\n  OLD_PLUGIN=y\nfi\n\nKW=kwriteconfig6; command -v $KW >/dev/null || KW=kwriteconfig5\nKR=kreadconfig6;  command -v $KR >/dev/null || KR=kreadconfig5\n\n# Meta+V question: asked once, answer remembered; defaults to yes without a terminal\nmkdir -p "$CONF_DIR"\nUSE_META_V=$(sed -n \'s/^META_V=//p\' "$CONF_DIR/setup.conf" 2>/dev/null || true)\nif [ -z "$USE_META_V" ]; then\n  USE_META_V=y\n  if [ -t 0 ]; then\n    read -r -p "Use Meta+V for the new clipboard history (instead of Plasma\'s)? [Y/n] " ans || ans=\n    case "$ans" in [nN]*) USE_META_V=n ;; esac\n  fi\n  echo "META_V=$USE_META_V" >> "$CONF_DIR/setup.conf"\nfi\n# remember how things were before we changed them, so --uninstall can put them back\nremember() { grep -q "^$1=" "$CONF_DIR/setup.conf" 2>/dev/null || echo "$1=$2" >> "$CONF_DIR/setup.conf"; }\nif busctl --user get-property org.a11y.Bus /org/a11y/bus org.a11y.Status IsEnabled 2>/dev/null | grep -q true; then\n  remember A11Y_WAS_ON true\nelse\n  remember A11Y_WAS_ON false\nfi\n\necho "==> Installing dependencies (asks for your password)"\nsudo apt-get update -qq || echo "!!  apt update failed (no network?); using the package lists you have"\nsudo apt-get install -y python3-pyqt6 python3-pyqt6.qtsvg fonts-noto-color-emoji wl-clipboard \\\n    python3-gi gir1.2-atspi-2.0 at-spi2-core \\\n    git curl meson ninja-build gcc pkg-config libwayland-dev libwayland-bin wayland-protocols\n\n# Plasma 6 only offers the newer "ext-data-control" clipboard protocol. Ubuntu\'s\n# wl-clipboard is too old for it, so build wl-clipboard 2.3.0 into your home folder.\n# Downloads are pinned to exact versions and checked, since this tool sees every copy.\nWLC="$HOME/.local/opt/$APP/wl-clipboard"\nWLC_COMMIT=67a7b937895bceec1ae5ccebb10216f63f70ca1b          # wl-clipboard v2.3.0\nXML_SHA256=293deba5dfdb974fbcf8dcf891a30a51a36a8bba0047dc6bdf6a03194089b7fb   # wayland-protocols 1.45\nXML="$HOME/.local/opt/$APP/ext-data-control-v1.xml"\nget_xml() {   # the clipboard protocol description, downloaded once and checked\n  if ! echo "$XML_SHA256  $XML" 2>/dev/null | sha256sum -c --quiet 2>/dev/null; then\n    mkdir -p "$(dirname "$XML")"\n    curl -fsSL -o "$XML.tmp" \\\n        https://gitlab.freedesktop.org/wayland/wayland-protocols/-/raw/1.45/staging/ext-data-control/ext-data-control-v1.xml || return 1\n    if ! echo "$XML_SHA256  $XML.tmp" | sha256sum -c --quiet; then\n      echo "!!  Protocol file checksum mismatch; not using it."; rm -f "$XML.tmp"; return 1\n    fi\n    mv "$XML.tmp" "$XML"\n  fi\n}\nbuild_wlc() {\n  local WORK; WORK=$(mktemp -d)\n  trap \'rm -rf "$WORK"\' RETURN\n  git -c advice.detachedHead=false clone -q --depth 1 --branch v2.3.0 \\\n      https://github.com/bugaevc/wl-clipboard.git "$WORK/src" || return 1\n  if [ "$(git -C "$WORK/src" rev-parse HEAD)" != "$WLC_COMMIT" ]; then\n    echo "!!  wl-clipboard download doesn\'t match the expected version; not using it."; return 1\n  fi\n  get_xml || return 1\n  cp "$XML" "$WORK/src/src/protocol/ext-data-control-v1.xml"\n  # use that bundled protocol file even if the system\'s wayland-protocols is older\n  sed -i -e "s|have_ext_data_control = wayland_protocols.found() and wayland_protocols.version().version_compare(\'>= 1.39\')|have_ext_data_control = true|" \\\n         -e "s|ext_data_control_xml = join_paths(protocols_path, \'staging\', \'ext-data-control\', \'ext-data-control-v1.xml\')|ext_data_control_xml = \'ext-data-control-v1.xml\'|" \\\n      "$WORK/src/src/protocol/meson.build"\n  meson setup "$WORK/build" "$WORK/src" --prefix="$WLC" --buildtype=release \\\n      -Dzshcompletiondir=no -Dfishcompletiondir=no >/dev/null || return 1\n  ninja -C "$WORK/build" >/dev/null || return 1\n  ninja -C "$WORK/build" install >/dev/null || return 1\n}\nif ! "$WLC/bin/wl-paste" --version 2>/dev/null | grep -q "2\\.[3-9]"; then\n  echo "==> Building wl-clipboard 2.3.0 (for clipboard history, takes ~20 seconds)"\n  if build_wlc; then\n    echo "    built: $("$WLC/bin/wl-paste" --version | head -1)"\n  else\n    echo "!!  Couldn\'t build wl-clipboard (network?). Clipboard history won\'t work until setup is re-run."\n  fi\nfi\n\n# kaomi-copy: puts several formats on the clipboard at once (wl-copy can do one),\n# so restoring your clipboard after an emoji keeps formatting. Tiny C program,\n# source written next to this by "kaomi.py --setup"; rebuilt when it changes.\nKC="$HOME/.local/opt/$APP/kaomi-copy"\nif [ -f "$KC/kaomi-copy.c" ] && [ "$(sha256sum "$KC/kaomi-copy.c" | cut -c1-64)" != "$(cat "$KC/built-from" 2>/dev/null)" ]; then\n  echo "==> Building kaomi-copy (keeps clipboard formatting)"\n  if get_xml && (\n       cd "$KC" && rm -rf build && mkdir build &&\n       wayland-scanner client-header "$XML" build/ext-data-control-v1-client-protocol.h &&\n       wayland-scanner private-code "$XML" build/ext-data-control-v1-protocol.c &&\n       gcc -O2 -Wall -Ibuild -o build/kaomi-copy kaomi-copy.c build/ext-data-control-v1-protocol.c \\\n           -lwayland-client &&\n       mkdir -p bin && install -m 755 build/kaomi-copy bin/kaomi-copy &&\n       sha256sum kaomi-copy.c | cut -c1-64 > built-from ); then\n    echo "    built"\n  else\n    echo "!!  Couldn\'t build kaomi-copy; clipboard restores will use wl-copy (plain text only)."\n  fi\nfi\n\n# Auto-insert now uses KDE\'s own permission prompt. Older versions gave every\n# program in your session access to a virtual keyboard; take that back.\nif [ -e /etc/udev/rules.d/60-win-emoji-picker-uinput.rules ] || [ -e /etc/modules-load.d/win-emoji-picker-uinput.conf ]; then\n  echo "==> Removing the old virtual-keyboard access (no longer needed)"\n  sudo rm -f /etc/udev/rules.d/60-win-emoji-picker-uinput.rules /etc/modules-load.d/win-emoji-picker-uinput.conf\n  sudo udevadm control --reload-rules || true\n  UINPUT_REMOVED=y\nfi\n\nif [ "${OLD_PLUGIN:-n}" = y ]; then\n  for d in "$(qtpaths6 --query QT_INSTALL_PLUGINS 2>/dev/null)" /usr/lib/*/qt6/plugins /usr/lib64/qt6/plugins /usr/lib/qt6/plugins; do\n    f="$d/kwin/plugins/kaomi_caret.so"\n    if [ -n "$d" ] && [ -e "$f" ]; then sudo rm -f "$f"; fi\n  done\nfi\n\necho "==> Installing the app"\nmkdir -p "$HOME/.local/bin" "$HOME/.local/share/applications" "$HOME/.config/autostart" "$HOME/.cache"\n[ "$SRC" -ef "$BIN" ] || install -m 755 "$SRC" "$BIN"      # re-running from the installed copy is fine\n\ncat > "$HOME/.local/share/applications/$APP.desktop" <<EOF\n[Desktop Entry]\nType=Application\nName=Kaomi\nGenericName=Emoji Picker\nComment=Pick an emoji and type it into the current app\nExec=$BIN\nIcon=$APP\nTerminal=false\nCategories=Utility;\nStartupNotify=false\nEOF\n\ncat > "$HOME/.local/share/applications/$APP-clipboard.desktop" <<EOF\n[Desktop Entry]\nType=Application\nName=Kaomi Clipboard\nGenericName=Clipboard History\nComment=Open Kaomi on its clipboard history tab\nExec=$BIN --clipboard\nIcon=$APP-clipboard\nTerminal=false\nCategories=Utility;\nStartupNotify=false\nEOF\n\ncat > "$HOME/.config/autostart/$APP-daemon.desktop" <<EOF\n[Desktop Entry]\nType=Application\nName=Kaomi background service\nExec=$BIN --daemon\nIcon=$APP\nNoDisplay=true\nX-KDE-autostart-phase=2\nEOF\n\necho "==> Shortcuts"\n# Plasma\'s shortcut service keeps its own copy of these settings and writes it\n# back, so it is stopped while we edit and started again afterwards.\ndeclare -a EDITS=()\nwant() {  # group subgroup key value   (queue only if different)\n  local cur; cur=$($KR --file kglobalshortcutsrc --group "$1" ${2:+--group "$2"} --key "$3")\n  [ "$cur" = "$4" ] || EDITS+=("$1|$2|$3|$4")\n}\ndrop() {  # group subgroup key   (queue a delete if it is set)\n  local cur; cur=$($KR --file kglobalshortcutsrc --group "$1" ${2:+--group "$2"} --key "$3")\n  [ -z "$cur" ] || EDITS+=("$1|$2|$3|<delete>")\n}\ndrop services "$OLD.desktop" _launch            # shortcuts of the old name\ndrop services "$OLD-clipboard.desktop" _launch\nEMOJIER=$($KR --file kglobalshortcutsrc --group services --group org.kde.plasma.emojier.desktop --key _launch)\n[ "$EMOJIER" = "Meta+Ctrl+Alt+Shift+Space" ] || remember ORIG_EMOJIER "${EMOJIER:-<default>}"\nwant services org.kde.plasma.emojier.desktop _launch "Meta+Ctrl+Alt+Shift+Space"\nwant services "$APP.desktop" _launch "Meta+."\nif [ "$USE_META_V" = y ]; then\n  for comp in plasmashell klipper; do\n    cur=$($KR --file kglobalshortcutsrc --group $comp --key show-on-mouse-pos)\n    if [ -n "$cur" ] && [ "${cur%%,*}" != "none" ]; then\n      remember "ORIG_SHOW_ON_MOUSE_$comp" "$cur"\n      want $comp "" show-on-mouse-pos "none,${cur#*,}"\n    fi\n  done\n  want services "$APP-clipboard.desktop" _launch "Meta+V"\nfi\nNEED_RELOGIN=n\nif [ ${#EDITS[@]} -gt 0 ]; then\n  KGA=plasma-kglobalaccel.service\n  HAVE_KGA=n; systemctl --user is-active --quiet $KGA 2>/dev/null && HAVE_KGA=y\n  [ $HAVE_KGA = y ] && systemctl --user stop $KGA\n  trap \'[ $HAVE_KGA = y ] && systemctl --user start $KGA\' EXIT    # even if something below fails\n  for e in "${EDITS[@]}"; do\n    IFS=\'|\' read -r g sg k v <<< "$e"\n    if [ "$v" = "<delete>" ]; then\n      $KW --file kglobalshortcutsrc --group "$g" ${sg:+--group "$sg"} --key "$k" --delete\n    else\n      $KW --file kglobalshortcutsrc --group "$g" ${sg:+--group "$sg"} --key "$k" "$v"\n    fi\n  done\n  trap - EXIT\n  if [ $HAVE_KGA = y ]; then\n    systemctl --user start $KGA\n    echo "    updated (active now)"\n  else\n    NEED_RELOGIN=y\n    echo "    updated (active after you log out and back in)"\n  fi\nelse\n  echo "    already set"\nfi\n\necho "==> Plasma\'s own clipboard (Klipper)"\n# Klipper\'s "Prevent empty clipboard" puts its own last item straight back\n# whenever the clipboard is emptied. That undid Kaomi\'s Clear all and Delete\n# (old items came back), so it is turned off. --uninstall puts it back.\nCUR=$($KR --file klipperrc --group General --key NoEmptyClipboard --default true)\nif [ "$CUR" != false ]; then\n  remember ORIG_NO_EMPTY_CLIPBOARD "$CUR"\n  $KW --file klipperrc --group General --key NoEmptyClipboard --type bool false\n  busctl --user call org.kde.klipper /klipper org.kde.klipper.klipper reloadConfig >/dev/null 2>&1 || true\n  echo "    Prevent empty clipboard: turned off (Kaomi looks after the clipboard now)"\nelse\n  echo "    already set"\nfi\n\n# Older versions used a KWin window rule; the picker now does this itself (safer:\n# a rule could be borrowed by any app using the same name). Remove it cleanly.\nRULE="$OLD-rule"\nif [ -n "$($KR --file kwinrulesrc --group "$RULE" --key wmclass)" ]; then\n  for k in Description wmclass wmclassmatch above aboverule skiptaskbar skiptaskbarrule \\\n           skippager skippagerrule skipswitcher skipswitcherrule placement placementrule; do\n    $KW --file kwinrulesrc --group "$RULE" --key $k --delete 2>/dev/null || true\n  done\n  for list in rules Order; do\n    cur=$($KR --file kwinrulesrc --group General --key $list)\n    [ -n "$cur" ] || continue\n    new=$(printf \'%s\' "$cur" | tr \',\' \'\\n\' | grep -vx "$RULE" | paste -sd, - || true)\n    $KW --file kwinrulesrc --group General --key $list "$new"\n    if [ $list = rules ]; then\n      $KW --file kwinrulesrc --group General --key count "$(printf \'%s\' "$new" | tr \',\' \'\\n\' | grep -c . || true)"\n    fi\n  done\n  for Q in qdbus6 qdbus; do\n    command -v $Q >/dev/null && { $Q org.kde.KWin /KWin reconfigure >/dev/null 2>&1 || true; break; }\n  done\nfi\n\necho "==> Text-cursor plugin for KWin (panel opens at the text cursor in every app)"\n# Installed as a root-owned system file but only switched on by the picker for\n# your session. After a Plasma update the picker shows an "Update now" notification.\nif ! ( set -o pipefail; "$BIN" --update-kwin-plugin 2>&1 | sed \'s/^/    /\' ); then\n  echo "!!  The plugin couldn\'t be built; the panel will use the older per-app method."\nfi\n\necho "==> Starting it"\n"$BIN" --quit 2>/dev/null || true                         # ask the running picker to exit\nsleep 0.5\n# older versions don\'t know --quit: stop only the picker\'s own processes\npkill -u "$(id -u)" -f -x "[^ ]*python3[^ ]* $BIN( --daemon| --clipboard)?" 2>/dev/null || true\npkill -u "$(id -u)" -f "$APP-caret-helper" 2>/dev/null || true\nsleep 0.3\n(umask 077; nohup "$BIN" --daemon >/dev/null 2>"$HOME/.cache/$APP.start.log" &)\nsleep 2\nif pgrep -u "$(id -u)" -f -x "[^ ]*python3[^ ]* $BIN --daemon" >/dev/null; then\n  echo "    running: $("$BIN" --version)"\n  case "$("$BIN" --kplug-status 2>/dev/null)" in\n    active)   echo "    KWin plugin: active" ;;\n    outdated) echo "    KWin plugin: updated; Plasma still runs the old one until you log out and back in"\n              NEED_RELOGIN=y ;;\n    *)        echo "    KWin plugin: turns on after you log out and back in" ;;\n  esac\nelse\n  echo "!!  It crashed on start. Error:"; tail -15 "$HOME/.cache/$APP.start.log" "$HOME/.cache/$APP.log" 2>/dev/null\nfi\n\necho "==> Checking clipboard access"\nif [ -n "$WAYLAND_DISPLAY" ] && [ -x "$WLC/bin/wl-paste" ]; then\n  ERR=$(timeout 2 "$WLC/bin/wl-paste" --watch true 2>&1 >/dev/null || true)\n  if echo "$ERR" | grep -qi "require\\|not support\\|protocol"; then\n    echo "!!  Clipboard history can\'t watch copies on this system: $ERR"\n  else\n    echo "    ok"\n  fi\nfi\n\necho\nif [ ! -e "$HOME/.local/share/$APP/portal-token" ]; then\n  echo "KDE will ask once to allow Kaomi to \\"control input devices\\"."\n  echo "Click Allow: that\'s how it pastes clipboard items for you. You\'ll see a short"\n  echo "\\"Remote control session started\\" notice once per login."\nfi\nif [ "${UINPUT_REMOVED:-n}" = y ]; then\n  echo "(The old virtual-keyboard access is fully gone after your next restart.)"\nfi\nif [ "$NEED_RELOGIN" = y ]; then\n  echo "Done! Log out and back in once so the new shortcuts / plugin take over."\nelse\n  echo "Done! Everything is up to date and running."\nfi\n'
UNINSTALL_SH = '#!/usr/bin/env bash\n# Removes Kaomi: app files, shortcuts, KWin plugin, background service.\n# Run:  kaomi --uninstall\nAPP=kaomi\nBIN="$HOME/.local/bin/$APP"\n\nif [ "$(id -u)" -eq 0 ]; then\n  echo "Run this as your normal user (without sudo). It asks for your password when needed."\n  exit 1\nfi\nKW=kwriteconfig6; command -v $KW >/dev/null || KW=kwriteconfig5\nKR=kreadconfig6;  command -v $KR >/dev/null || KR=kreadconfig5\nSETUP_CONF="$HOME/.config/$APP/setup.conf"\nsaved() { sed -n "s/^$1=//p" "$SETUP_CONF" 2>/dev/null | head -1; }\n\necho "==> Stopping the picker"\n[ -x "$BIN" ] && "$BIN" --quit 2>/dev/null\nsleep 0.5\npkill -u "$(id -u)" -f -x "[^ ]*python3[^ ]* $BIN( --daemon| --clipboard)?" 2>/dev/null\npkill -u "$(id -u)" -f "$APP-caret-helper" 2>/dev/null\nfor Q in qdbus6 qdbus; do\n  command -v $Q >/dev/null && { $Q org.kde.KWin /Scripting org.kde.kwin.Scripting.unloadScript \\\n      "$APP-helper" >/dev/null 2>&1; break; }\ndone\n\necho "==> Giving the shortcuts back to Plasma"\nKGA=plasma-kglobalaccel.service\nHAVE_KGA=n; systemctl --user is-active --quiet $KGA 2>/dev/null && HAVE_KGA=y\n[ $HAVE_KGA = y ] && systemctl --user stop $KGA\nEMOJIER=$(saved ORIG_EMOJIER)\nif [ "$EMOJIER" = "<default>" ]; then\n  $KW --file kglobalshortcutsrc --group services --group org.kde.plasma.emojier.desktop --key _launch --delete\nelif [ -n "$EMOJIER" ]; then\n  $KW --file kglobalshortcutsrc --group services --group org.kde.plasma.emojier.desktop --key _launch "$EMOJIER"\nfi    # (nothing saved: setup never changed it, so leave it alone)\n$KW --file kglobalshortcutsrc --group services --group "$APP.desktop" --key _launch --delete\n$KW --file kglobalshortcutsrc --group services --group "$APP-clipboard.desktop" --key _launch --delete\nfor comp in plasmashell klipper; do\n  cur=$($KR --file kglobalshortcutsrc --group $comp --key show-on-mouse-pos)\n  orig=$(saved "ORIG_SHOW_ON_MOUSE_$comp")\n  case "$cur" in\n    none,*) $KW --file kglobalshortcutsrc --group $comp --key show-on-mouse-pos "${orig:-Meta+V,${cur#none,}}" ;;\n  esac\ndone\n[ $HAVE_KGA = y ] && systemctl --user start $KGA\n\n# Klipper\'s "Prevent empty clipboard", as it was before setup\nORIG=$(saved ORIG_NO_EMPTY_CLIPBOARD)\nif [ -n "$ORIG" ]; then\n  if [ "$ORIG" = true ]; then\n    $KW --file klipperrc --group General --key NoEmptyClipboard --delete\n  else\n    $KW --file klipperrc --group General --key NoEmptyClipboard --type bool "$ORIG"\n  fi\n  busctl --user call org.kde.klipper /klipper org.kde.klipper.klipper reloadConfig >/dev/null 2>&1\nfi\n\n# window rule used by older versions\nRULE="win-emoji-picker-rule"\nif [ -n "$($KR --file kwinrulesrc --group "$RULE" --key wmclass)" ]; then\n  for k in Description wmclass wmclassmatch above aboverule skiptaskbar skiptaskbarrule \\\n           skippager skippagerrule skipswitcher skipswitcherrule placement placementrule; do\n    $KW --file kwinrulesrc --group "$RULE" --key $k --delete 2>/dev/null\n  done\n  for list in rules Order; do\n    cur=$($KR --file kwinrulesrc --group General --key $list)\n    [ -n "$cur" ] || continue\n    new=$(printf \'%s\' "$cur" | tr \',\' \'\\n\' | grep -vx "$RULE" | paste -sd, -)\n    $KW --file kwinrulesrc --group General --key $list "$new"\n    [ $list = rules ] && $KW --file kwinrulesrc --group General --key count \\\n        "$(printf \'%s\' "$new" | tr \',\' \'\\n\' | grep -c .)"\n  done\n  for Q in qdbus6 qdbus; do\n    command -v $Q >/dev/null && { $Q org.kde.KWin /KWin reconfigure >/dev/null 2>&1; break; }\n  done\nfi\n\necho "==> Removing the KWin text-cursor plugin (asks for your password)"\nfor d in "$(qtpaths6 --query QT_INSTALL_PLUGINS 2>/dev/null)" /usr/lib/*/qt6/plugins /usr/lib64/qt6/plugins /usr/lib/qt6/plugins; do\n  f="$d/kwin/plugins/kaomi_caret.so"\n  [ -n "$d" ] && [ -e "$f" ] && sudo rm -f "$f" && echo "    removed $f"\ndone\n\nrm -f "$HOME/.local/share/$APP/portal-token"      # KDE input permission token\n\nif [ -e /etc/udev/rules.d/60-win-emoji-picker-uinput.rules ] || [ -e /etc/modules-load.d/win-emoji-picker-uinput.conf ]; then\n  echo "==> Removing the virtual keyboard permission (older versions)"\n  sudo rm -f /etc/udev/rules.d/60-win-emoji-picker-uinput.rules /etc/modules-load.d/win-emoji-picker-uinput.conf\n  sudo udevadm control --reload-rules\n  echo "    (takes full effect after a restart)"\nfi\n\necho "==> Removing app files"\nrm -f "$BIN" "$HOME/.local/share/applications/$APP.desktop" \\\n      "$HOME/.local/share/applications/$APP-clipboard.desktop" \\\n      "$HOME/.config/autostart/$APP-daemon.desktop" "$HOME/.cache/$APP".*log* \\\n      "$HOME/.local/share/icons/hicolor/scalable/apps/$APP.svg" \\\n      "$HOME/.local/share/icons/hicolor/scalable/apps/$APP-clipboard.svg"\nrm -rf "$HOME/.local/opt/$APP" "$HOME/.local/share/$APP/kwin-helper.js"\n\n# accessibility: switch it back off only if it was off before setup turned it on\nif [ "$(saved A11Y_WAS_ON)" = false ] && \\\n   ! busctl --user get-property org.a11y.Bus /org/a11y/bus org.a11y.Status ScreenReaderEnabled 2>/dev/null | grep -q true; then\n  busctl --user set-property org.a11y.Bus /org/a11y/bus org.a11y.Status IsEnabled b false 2>/dev/null\nfi\n\nKEEP=y\nif [ -t 0 ]; then\n  read -r -p "Also delete your settings and pinned clipboard items? [y/N] " ans || ans=\n  case "$ans" in [yY]*) KEEP=n ;; esac\nfi\nif [ $KEEP = n ]; then\n  rm -rf "$HOME/.config/$APP" "$HOME/.local/share/$APP"\n  echo "    settings and pinned items deleted"\nelse\n  # the "how things were before setup" notes are used up: a later setup must look again\n  sed -i \'/^ORIG_/d;/^A11Y_WAS_ON=/d\' "$SETUP_CONF" 2>/dev/null\n  echo "    kept your settings (~/.config/$APP) and pinned items (~/.local/share/$APP)"\nfi\necho\necho "Uninstalled."\n'
ICONS = {"": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">\n  <defs>\n    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#6A8CFF"/><stop offset="1" stop-color="#4B5FE0"/></linearGradient>\n    <linearGradient id="face" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFE27A"/><stop offset="1" stop-color="#FFC530"/></linearGradient>\n  </defs>\n  <rect x="4" y="4" width="56" height="56" rx="14" fill="url(#bg)"/>\n  <circle cx="32" cy="33" r="17" fill="url(#face)"/>\n  <ellipse cx="25.5" cy="29" rx="2.4" ry="3.3" fill="#3A2A1A"/>\n  <ellipse cx="38.5" cy="29" rx="2.4" ry="3.3" fill="#3A2A1A"/>\n  <path d="M23.5 37.5 Q32 46 40.5 37.5" fill="none" stroke="#3A2A1A" stroke-width="2.8" stroke-linecap="round"/>\n</svg>\n',
         "-clipboard": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">\n  <defs>\n    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#6A8CFF"/><stop offset="1" stop-color="#4B5FE0"/></linearGradient>\n  </defs>\n  <rect x="4" y="4" width="56" height="56" rx="14" fill="url(#bg)"/>\n  <rect x="17" y="14" width="30" height="38" rx="5" fill="#F4F6FF"/>\n  <rect x="25" y="10.5" width="14" height="8" rx="3" fill="#FFC530" stroke="#4B5FE0" stroke-width="1.5"/>\n  <rect x="22.5" y="26" width="19" height="3" rx="1.5" fill="#9AA6D8"/>\n  <rect x="22.5" y="33" width="19" height="3" rx="1.5" fill="#9AA6D8"/>\n  <rect x="22.5" y="40" width="12" height="3" rx="1.5" fill="#9AA6D8"/>\n</svg>\n'}

KAOMI_COPY_C = '/* kaomi-copy: put several formats on the Wayland clipboard at once.\n *\n * wl-copy can offer one format; a clipboard restored through it loses its\n * formatting (HTML, file lists). This does the same job with any number of\n * formats, over the same "ext-data-control" protocol Plasma 6 offers to\n * clipboard managers.\n *\n * Usage:  kaomi-copy [--primary] < records\n * stdin:  zero or more records, each "<mime> <byte count>\\n" followed by that\n *         many bytes. No records = empty the clipboard.\n * Exits as soon as the clipboard is set (like wl-copy); a forked child keeps\n * serving the data until something else is copied.\n */\n#define _GNU_SOURCE\n#include <errno.h>\n#include <fcntl.h>\n#include <signal.h>\n#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n#include <sys/wait.h>\n#include <unistd.h>\n#include <wayland-client.h>\n#include "ext-data-control-v1-client-protocol.h"\n\nstruct record {\n    char *mime;\n    unsigned char *data;\n    size_t len;\n};\n\nstatic struct record *records;\nstatic size_t nrecords;\nstatic struct wl_seat *seat;\nstatic struct ext_data_control_manager_v1 *manager;\nstatic int done;\n\nstatic void fail(const char *msg)\n{\n    fprintf(stderr, "kaomi-copy: %s\\n", msg);\n    exit(1);\n}\n\n/* ---- reading stdin ---- */\nstatic int read_all(unsigned char *buf, size_t len)\n{\n    while (len > 0) {\n        ssize_t n = read(0, buf, len);\n        if (n < 0 && errno == EINTR) {\n            continue;\n        }\n        if (n <= 0) {\n            return -1;\n        }\n        buf += n;\n        len -= (size_t)n;\n    }\n    return 0;\n}\n\nstatic void read_records(void)\n{\n    char line[512];\n    for (;;) {\n        size_t i = 0;\n        for (;;) {\n            char c;\n            ssize_t n = read(0, &c, 1);\n            if (n < 0 && errno == EINTR) {\n                continue;\n            }\n            if (n <= 0) {\n                if (i == 0) {\n                    return; /* clean end of input */\n                }\n                fail("unexpected end of input");\n            }\n            if (c == \'\\n\') {\n                break;\n            }\n            if (i + 1 >= sizeof line) {\n                fail("header line too long");\n            }\n            line[i++] = c;\n        }\n        line[i] = \'\\0\';\n        char *sp = strrchr(line, \' \');\n        if (!sp || sp == line) {\n            fail("bad header line");\n        }\n        *sp = \'\\0\';\n        char *end;\n        unsigned long long len = strtoull(sp + 1, &end, 10);\n        if (*end != \'\\0\' || len > (1ULL << 31)) {\n            fail("bad length");\n        }\n        struct record r;\n        r.mime = strdup(line);\n        r.len = (size_t)len;\n        r.data = malloc(r.len ? r.len : 1);\n        if (!r.mime || !r.data) {\n            fail("out of memory");\n        }\n        if (read_all(r.data, r.len) < 0) {\n            fail("truncated data");\n        }\n        records = realloc(records, (nrecords + 1) * sizeof *records);\n        if (!records) {\n            fail("out of memory");\n        }\n        records[nrecords++] = r;\n    }\n}\n\n/* ---- wayland ---- */\nstatic void registry_global(void *data, struct wl_registry *reg, uint32_t name,\n                            const char *iface, uint32_t version)\n{\n    (void)data;\n    (void)version;\n    if (strcmp(iface, wl_seat_interface.name) == 0 && !seat) {\n        seat = wl_registry_bind(reg, name, &wl_seat_interface, 1);\n    } else if (strcmp(iface, ext_data_control_manager_v1_interface.name) == 0) {\n        manager = wl_registry_bind(reg, name, &ext_data_control_manager_v1_interface, 1);\n    }\n}\n\nstatic void registry_global_remove(void *data, struct wl_registry *reg, uint32_t name)\n{\n    (void)data;\n    (void)reg;\n    (void)name;\n}\n\nstatic const struct wl_registry_listener registry_listener = {registry_global, registry_global_remove};\n\nstatic void source_send(void *data, struct ext_data_control_source_v1 *src, const char *mime, int32_t fd)\n{\n    (void)data;\n    (void)src;\n    for (size_t i = 0; i < nrecords; i++) {\n        if (strcmp(records[i].mime, mime) != 0) {\n            continue;\n        }\n        const unsigned char *p = records[i].data;\n        size_t left = records[i].len;\n        /* the reader may be slow: block on this fd only */\n        int flags = fcntl(fd, F_GETFL);\n        if (flags >= 0) {\n            fcntl(fd, F_SETFL, flags & ~O_NONBLOCK);\n        }\n        while (left > 0) {\n            ssize_t n = write(fd, p, left);\n            if (n < 0 && errno == EINTR) {\n                continue;\n            }\n            if (n <= 0) {\n                break;\n            }\n            p += n;\n            left -= (size_t)n;\n        }\n        break;\n    }\n    close(fd);\n}\n\nstatic void source_cancelled(void *data, struct ext_data_control_source_v1 *src)\n{\n    (void)data;\n    ext_data_control_source_v1_destroy(src);\n    done = 1;\n}\n\nstatic const struct ext_data_control_source_v1_listener source_listener = {source_send, source_cancelled};\n\n/* offers the compositor tells us about: not needed, just tidy them away */\nstatic void offer_offer(void *data, struct ext_data_control_offer_v1 *offer, const char *mime)\n{\n    (void)data;\n    (void)offer;\n    (void)mime;\n}\n\nstatic const struct ext_data_control_offer_v1_listener offer_listener = {offer_offer};\n\nstatic void device_data_offer(void *data, struct ext_data_control_device_v1 *dev,\n                              struct ext_data_control_offer_v1 *offer)\n{\n    (void)data;\n    (void)dev;\n    ext_data_control_offer_v1_add_listener(offer, &offer_listener, NULL);\n}\n\nstatic void device_selection(void *data, struct ext_data_control_device_v1 *dev,\n                             struct ext_data_control_offer_v1 *offer)\n{\n    (void)data;\n    (void)dev;\n    if (offer) {\n        ext_data_control_offer_v1_destroy(offer);\n    }\n}\n\nstatic void device_finished(void *data, struct ext_data_control_device_v1 *dev)\n{\n    (void)data;\n    (void)dev;\n    done = 1;\n}\n\nstatic const struct ext_data_control_device_v1_listener device_listener = {\n    device_data_offer, device_selection, device_finished, device_selection};\n\nint main(int argc, char **argv)\n{\n    int primary = 0;\n    for (int i = 1; i < argc; i++) {\n        if (strcmp(argv[i], "--primary") == 0) {\n            primary = 1;\n        } else {\n            fail("usage: kaomi-copy [--primary] < records");\n        }\n    }\n    read_records();\n\n    struct wl_display *display = wl_display_connect(NULL);\n    if (!display) {\n        fail("can\'t connect to the Wayland display");\n    }\n    struct wl_registry *registry = wl_display_get_registry(display);\n    wl_registry_add_listener(registry, &registry_listener, NULL);\n    wl_display_roundtrip(display);\n    if (!seat) {\n        fail("no seat");\n    }\n    if (!manager) {\n        fail("the compositor doesn\'t offer ext-data-control (Plasma 6.1 or newer needed)");\n    }\n\n    struct ext_data_control_device_v1 *device = ext_data_control_manager_v1_get_data_device(manager, seat);\n    ext_data_control_device_v1_add_listener(device, &device_listener, NULL);\n\n    struct ext_data_control_source_v1 *source = NULL;\n    if (nrecords > 0) {\n        source = ext_data_control_manager_v1_create_data_source(manager);\n        ext_data_control_source_v1_add_listener(source, &source_listener, NULL);\n        for (size_t i = 0; i < nrecords; i++) {\n            ext_data_control_source_v1_offer(source, records[i].mime);\n        }\n    }\n    if (primary) {\n        ext_data_control_device_v1_set_primary_selection(device, source);\n    } else {\n        ext_data_control_device_v1_set_selection(device, source);\n    }\n    wl_display_roundtrip(display); /* the clipboard is set once this returns */\n\n    if (!source) {\n        return 0; /* nothing to serve */\n    }\n    /* keep serving from the background; the caller only waits for "set" */\n    signal(SIGHUP, SIG_IGN);\n    pid_t pid = fork();\n    if (pid < 0) {\n        fail("fork failed");\n    }\n    if (pid > 0) {\n        return 0;\n    }\n    setsid();\n    close(0);\n    if (chdir("/") != 0) {\n        /* not important */\n    }\n    while (!done && wl_display_dispatch(display) >= 0) {\n    }\n    return 0;\n}\n'

if "--setup" in sys.argv or "--uninstall" in sys.argv:
    import subprocess, tempfile
    env = dict(os.environ, KAOMI_SRC=os.path.realpath(__file__))
    if "--setup" in sys.argv:                  # app icons for the menu and shortcuts
        icon_dir = os.path.expanduser("~/.local/share/icons/hicolor/scalable/apps")
        os.makedirs(icon_dir, exist_ok=True)
        for suffix, svg in ICONS.items():
            with open(os.path.join(icon_dir, APP_ID + suffix + ".svg"), "w") as f:
                f.write(svg)
        kc_dir = os.path.expanduser("~/.local/opt/kaomi/kaomi-copy")   # source for the installer to build
        os.makedirs(kc_dir, exist_ok=True)
        with open(os.path.join(kc_dir, "kaomi-copy.c"), "w") as f:
            f.write(KAOMI_COPY_C)
    # run from a temp file: with "bash -c", the script text would be in its own
    # command line and the "stop old copies" step (pkill -f) would match itself
    with tempfile.NamedTemporaryFile("w", suffix=".sh", prefix="kaomi-setup-", delete=False) as f:
        f.write(SETUP_SH if "--setup" in sys.argv else UNINSTALL_SH)
    try:
        code = subprocess.run(["bash", f.name], env=env).returncode
    finally:
        os.unlink(f.name)
    sys.exit(code)
def _runtime_dir():
    """Private per-user directory for the socket. Refuses a /tmp fallback that
    someone else created or that others can read."""
    d = os.environ.get("XDG_RUNTIME_DIR")
    if d and os.path.isdir(d):
        return d
    import stat
    d = f"/tmp/{APP_ID}-{os.getuid()}"
    try:
        os.mkdir(d, 0o700)
    except FileExistsError:
        pass
    st = os.lstat(d)
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid() or (st.st_mode & 0o077):
        sys.exit(f"{APP_ID}: {d} is not a private directory owned by you; refusing to run")
    return d


RUNTIME = _runtime_dir()
SOCK = os.path.join(RUNTIME, APP_ID + ".sock")
DAEMON = "--daemon" in sys.argv
MODE = "clipboard" if "--clipboard" in sys.argv else "emoji"


def try_client():
    """Fast path: if the picker is already running, just tell it to toggle."""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(1.0)
    try:
        s.connect(SOCK)
    except OSError:
        return False
    if "--quit" in sys.argv:
        s.sendall(b"quit\n")
    elif not DAEMON:
        token = os.environ.get("XDG_ACTIVATION_TOKEN", "")
        s.sendall(f"toggle {MODE} {token}\n".encode())
    s.close()
    return True


if "--quit" in sys.argv:          # stop the running picker (used by setup / uninstall)
    try_client()
    sys.exit(0)

CLI_ONLY = ("--update-kwin-plugin", "--build-kwin-plugin", "--setup", "--uninstall", "--kplug-status")
if __name__ == "__main__" and not any(f in sys.argv for f in CLI_ONLY) and try_client():
    sys.exit(0)

# ------------------------------------------------------ KWin text-cursor plugin --
# Every app that types through the input method tells KWin where its text cursor
# is. This tiny KWin plugin answers "where is it right now?" over D-Bus, so the
# panel can open at the text cursor in every app (Chrome included) with no
# per-app setup. It also reports clicks outside the panel (which no ordinary
# program can see on Wayland), so the panel closes like on Windows while your
# app keeps keyboard focus. It is installed as a normal root-owned system file. KWin refuses
# a plugin built for a different KWin version, so after a Plasma update the old one
# is simply not loaded; the picker then shows a notification with an "Update now"
# button (you type your password, it rebuilds, done).
KPLUG_ID = "kaomi_caret"
KPLUG_API = 8          # bump when the plugin gains abilities (matches Api() in main.cpp)
KPLUG_DIR = os.path.join(os.path.expanduser("~"), ".local", "opt", APP_ID, "kwin-plugin")
KPLUG_STAMP = os.path.join(KPLUG_DIR, "built-for")
KPLUG_FILES = {
    'main.cpp': '// Kaomi KWin plugin. Two small jobs, nothing else:\n//  1. tells Kaomi where the text cursor is (so the panel opens there)\n//  2. tells Kaomi when you click outside its panel (so it closes, like Windows),\n//     which no ordinary program can see on Wayland once another app has focus.\n//  3. while the panel is open, takes the Escape key: Kaomi gets it, no app does.\n//  4. in stay-open mode, takes clicks on the panel and hands them to Kaomi, so\n//     KWin never moves keyboard focus away from the app you\'re typing in (some\n//     apps, Gmail for one, lose their cursor position on a quick blur/refocus).\n//  5. types text into the focused app (TypeText) so it lands at the cursor with\n//     the formatting there. Apps that have an input-method connection (Chrome\n//     does) get it the way an input method commits text; this works for any\n//     character. Other apps get keystrokes, sent straight to that app the way\n//     KWin\'s own input-method support does it: a character that isn\'t on your\n//     layout goes on F24 with a one-off keymap for that app only, then your\n//     keymap is sent back. KWin\'s own keyboard state is never touched.\n//     (Keystrokes alone can\'t do it for Chrome: it drops any typed character\n//     above U+FFFF, which is most emoji.)\n// Only the process that registered as Kaomi (first come, until it quits) may\n// use these. Apart from those, it only watches and never changes or blocks any input.\n#ifndef KAOMI_KWIN_VER\n#define KAOMI_KWIN_VER 699 // major*100+minor, set by CMake from KWin\'s version\n#endif\n#include "input.h"\n#if KAOMI_KWIN_VER >= 606\n#include "keyboard_input.h"\n#include "wayland/display.h"\n#include "wayland/keyboard.h"\n#include "wayland/seat.h"\n#include "wayland/textinput_v3.h"\n#include "wayland_server.h"\n#include "xkb.h"\n#endif\n#include "input_event.h"\n#include "input_event_spy.h"\n#include "inputmethod.h"\n#include "main.h"\n#include "plugin.h"\n#include "window.h"\n#include "workspace.h"\n\n#include <QDBusConnection>\n#include <QDBusConnectionInterface>\n#include <QDBusContext>\n#include <QDBusMessage>\n#include <QDBusServiceWatcher>\n#include <QElapsedTimer>\n#include <QPointer>\n#include <QList>\n#include <QTimer>\n#include <QPointF>\n#include <chrono>\n\n#ifndef KAOMI_KWIN_VER\n#define KAOMI_KWIN_VER 699 // major*100+minor, set by CMake from KWin\'s version\n#endif\n#if KAOMI_KWIN_VER >= 603\n#include "core/inputdevice.h"\n#endif\n\nnamespace KWin\n{\nclass MouseEvent;          // Plasma <= 6.2 (declared so both spellings below compile)\nclass KeyEvent;            // Plasma <= 6.2\nstruct PointerButtonEvent; // Plasma >= 6.3\nstruct KeyboardKeyEvent;   // Plasma >= 6.3\nstruct TouchDownEvent;     // Plasma >= 6.5\n}\n\nclass KaomiCaret;\n\n\n// Escape while the panel is open belongs to the panel, wherever keyboard focus\n// is. A filter (unlike a spy) can consume the key so no app sees it. It runs\n// after KWin\'s own global shortcuts, effects (Overview) and window move/resize,\n// so those keep their Escape; before any app.\nclass KaomiEscapeFilter : public KWin::InputEventFilter\n{\npublic:\n    explicit KaomiEscapeFilter(KaomiCaret *owner)\n        : KWin::InputEventFilter(KWin::InputFilterOrder::Popup)\n        , m_owner(owner)\n    {\n    }\n#if KAOMI_KWIN_VER >= 603\n    bool keyboardKey(KWin::KeyboardKeyEvent *event) override;\n    bool pointerButton(KWin::PointerButtonEvent *event) override;\n#else\n    bool keyEvent(KWin::KeyEvent *event) override;\n    bool pointerEvent(KWin::MouseEvent *event, quint32 nativeButton) override;\n#endif\n\nprivate:\n    bool handle(bool pressed, bool repeat, bool withModifiers);\n    bool click(const QPointF &pos, Qt::MouseButton button, bool pressed);\n    KaomiCaret *m_owner;\n    bool m_down = false;      // we swallowed an Escape press: swallow its release too\n    int m_clickDown = 0;      // buttons whose press we took: take their release too\n};\n\nclass KaomiCaret : public KWin::Plugin, public KWin::InputEventSpy, protected QDBusContext\n{\n    Q_OBJECT\n    Q_CLASSINFO("D-Bus Interface", "kaomi.Caret")\n\npublic:\n    KaomiCaret()\n        : m_escape(this)\n    {\n        QDBusConnection::sessionBus().registerObject(QStringLiteral("/KaomiCaret"), this,\n                                                     QDBusConnection::ExportScriptableSlots\n                                                         | QDBusConnection::ExportScriptableSignals);\n        if (KWin::input()) {\n            KWin::input()->installInputEventSpy(this);\n            KWin::input()->installInputEventFilter(&m_escape);\n        }\n        m_ownerWatch.setConnection(QDBusConnection::sessionBus());\n        m_ownerWatch.setWatchMode(QDBusServiceWatcher::WatchForUnregistration);\n        connect(&m_ownerWatch, &QDBusServiceWatcher::serviceUnregistered, this, [this](const QString &name) {\n            if (name == m_owner) {\n                forgetOwner(); // Kaomi quit: nobody may type until it registers again\n            }\n        });\n#if KAOMI_KWIN_VER >= 606\n        m_clock.start();\n        m_pump.setSingleShot(true);\n        m_pump.setInterval(5);\n        connect(&m_pump, &QTimer::timeout, this, &KaomiCaret::pump);\n        if (KWin::workspace()) {\n            connect(KWin::workspace(), &KWin::Workspace::windowActivated, this, [this]() {\n                m_activatedAt = m_clock.elapsed();\n            });\n        }\n#endif\n    }\n    ~KaomiCaret() override\n    {\n        if (KWin::input()) {\n            KWin::input()->uninstallInputEventFilter(&m_escape);\n            KWin::input()->uninstallInputEventSpy(this);\n        }\n        QDBusConnection::sessionBus().unregisterObject(QStringLiteral("/KaomiCaret"));\n    }\n\n    bool panelOpen() const\n    {\n        return !panels().isEmpty();\n    }\n\n    QList<KWin::Window *> panelWindows() const\n    {\n        return panels();\n    }\n\n    // In stay-open mode: the panel window under `pos`, if it is the topmost\n    // window there (not its tone menu, not a window on top of it)\n    KWin::Window *passivePanelAt(const QPointF &pos) const\n    {\n        if (!m_passive || !KWin::input()) {\n            return nullptr;\n        }\n        KWin::Window *top = KWin::input()->findToplevel(pos);\n        if (!top || top->isPopupWindow() || !panels().contains(top)) {\n            return nullptr;\n        }\n        return top;\n    }\n\n    void panelClicked(const QPointF &local, int button, bool pressed)\n    {\n        Q_EMIT PanelClicked(int(local.x()), int(local.y()), button, pressed);\n    }\n\n    void escapePressed()\n    {\n        Q_EMIT EscapePressed();\n    }\n\nQ_SIGNALS:\n    // A click or tap while Kaomi\'s panel is open, and not on the panel itself.\n    Q_SCRIPTABLE void ClickedOutside(int x, int y);\n    // Escape pressed while Kaomi\'s panel is open (wherever the keyboard focus\n    // was; the key was taken, no app received it).\n    Q_SCRIPTABLE void EscapePressed();\n    // Stay-open mode: a click on the panel, taken so the panel isn\'t activated.\n    // x, y are relative to the panel; button is a Qt::MouseButton value.\n    Q_SCRIPTABLE void PanelClicked(int x, int y, int button, bool pressed);\n\npublic Q_SLOTS:\n    // On-screen text cursor of the app you\'re typing in: [x, y, width, height],\n    // or an empty list when no app has an active text field.\n    Q_SCRIPTABLE QList<int> CursorRect() const\n    {\n        auto *im = KWin::kwinApp()->inputMethod();\n        if (!im) {\n            return {};\n        }\n        const auto r = im->cursorRectangle();\n        if (r.height() <= 0) {\n            return {};\n        }\n        return {int(r.x()), int(r.y()), int(r.width()), int(r.height())};\n    }\n\n    Q_SCRIPTABLE QString BuiltFor() const\n    {\n        return QStringLiteral(KWIN_PLUGIN_VERSION_STRING);\n    }\n\n    Q_SCRIPTABLE int Api() const\n    {\n        return 8;\n    }\n\n    // Whether text can be committed the way an input method does (the only way\n    // Chrome takes emoji). Built in (checked when the plugin is compiled for\n    // this KWin), so true whenever TypeText exists.\n    Q_SCRIPTABLE bool TextInputOk() const\n    {\n        return KAOMI_KWIN_VER >= 606;\n    }\n\n    // Which process is Kaomi (so no other window can pose as the panel). A\n    // process can only register itself, and only while no other live process\n    // is registered; it stays registered until it disconnects from the bus.\n    Q_SCRIPTABLE bool SetPanelPid(int pid)\n    {\n        if (!calledFromDBus()) {\n            return false;\n        }\n        const QString caller = message().service();\n        if (!m_owner.isEmpty() && m_owner != caller) {\n            return false; // taken by a process that is still running\n        }\n        if (callerPid() != pid) {\n            return false;\n        }\n        m_owner = caller;\n        m_pid = pid;\n        m_ownerWatch.setWatchedServices({caller});\n        return true;\n    }\n\n    // Type text into the focused app. Only Kaomi may call this. Requests are\n    // typed strictly in the order they came in, each one only once keyboard\n    // focus is on an app (never on Kaomi\'s own panel), so Kaomi can call this\n    // right after hiding its panel. Each request goes to the app that had focus\n    // when it was made (or the first app to get focus after the panel went\n    // away); if you switch to another app first, it is dropped. The answer\n    // comes when the text has been handed to the app: true; false = can\'t type\n    // this (too long, or never here), paste instead; or an error, and nothing\n    // was typed: kaomi.Caret.FocusOnPanel, kaomi.Caret.FocusMoved,\n    // kaomi.Caret.NoApp, kaomi.Caret.Locked (screen locked), kaomi.Caret.Busy.\n    Q_SCRIPTABLE bool TypeText(const QString &text)\n    {\n#if KAOMI_KWIN_VER < 606\n        Q_UNUSED(text)\n        return false; // needs KWin 6.6; Kaomi pastes instead\n#else\n        if (!isOwner() || text.isEmpty() || text.size() > maxTextLength) {\n            return false;\n        }\n        if (m_jobs.size() >= maxJobs) {\n            sendErrorReply(QStringLiteral("kaomi.Caret.Busy"), QStringLiteral("too many requests waiting"));\n            return false;\n        }\n        setDelayedReply(true);\n        Job job{text, message(), m_clock.elapsed(), {}, false};\n        KWin::Window *active = KWin::workspace() ? KWin::workspace()->activeWindow() : nullptr;\n        if (active && !isPanel(active)) {\n            job.target = active; // stay-open mode: the app you\'re typing in\n            job.targetSet = true;\n        }\n        m_jobs.append(job);\n        pump();\n        return false; // not sent: the real answer goes out from pump()\n#endif\n    }\n\n    // Stay-open mode on/off: while on, clicks on the panel go to Kaomi via\n    // PanelClicked instead of activating it.\n    Q_SCRIPTABLE void SetPassive(bool on)\n    {\n        if (isOwner()) {\n            m_passive = on;\n        }\n    }\n\nprivate:\n    bool isOwner() const\n    {\n        return calledFromDBus() && !m_owner.isEmpty() && message().service() == m_owner;\n    }\n\n    void forgetOwner()\n    {\n        m_owner.clear();\n        m_pid = 0;\n        m_passive = false;\n        m_ownerWatch.setWatchedServices({});\n#if KAOMI_KWIN_VER >= 606\n        m_jobs.clear(); // nobody left to answer\n        m_pump.stop();\n#endif\n    }\n\n    bool isPanel(KWin::Window *w) const\n    {\n        return w && m_pid > 0 && w->pid() == m_pid;\n    }\n\n    int callerPid() const\n    {\n        if (!calledFromDBus()) {\n            return -1;\n        }\n        const auto reply = connection().interface()->servicePid(message().service());\n        return reply.isValid() ? int(reply.value()) : -1;\n    }\n\n#if KAOMI_KWIN_VER >= 606\n    // How long a request may wait for focus to leave the panel. Kaomi gives up\n    // on an answer after 2 s, so this stays well under that.\n    static constexpr qint64 focusWaitMs = 1000;\n    // After a window switch, how long the newly focused app gets to turn its\n    // text input back on before it is sent keystrokes instead.\n    static constexpr qint64 textInputWaitMs = 200;\n    // Emoji and kaomoji are a few characters; anything longer is pasted.\n    static constexpr int maxTextLength = 256;\n    static constexpr int maxJobs = 64;\n\n    struct Job\n    {\n        QString text;\n        QDBusMessage msg;\n        qint64 queuedAt;\n        QPointer<KWin::Window> target;\n        bool targetSet;\n    };\n\n    static void fail(const Job &job, const char *name, const char *why)\n    {\n        QDBusConnection::sessionBus().send(job.msg.createErrorReply(QString::fromLatin1(name), QString::fromLatin1(why)));\n    }\n\n    static KWin::TextInputV3Interface *activeTextInput()\n    {\n        auto *ws = KWin::waylandServer();\n        if (!ws || !ws->seat()) {\n            return nullptr;\n        }\n        KWin::TextInputV3Interface *ti = ws->seat()->textInputV3();\n        return (ti && ti->isEnabled()) ? ti : nullptr;\n    }\n\n    void pump()\n    {\n        while (!m_jobs.isEmpty()) {\n            Job &job = m_jobs.first();\n            const qint64 t = m_clock.elapsed();\n            const qint64 waited = t - job.queuedAt;\n            if (KWin::waylandServer() && KWin::waylandServer()->isScreenLocked()) {\n                fail(m_jobs.takeFirst(), "kaomi.Caret.Locked", "the screen is locked");\n                continue;\n            }\n            KWin::Window *active = KWin::workspace() ? KWin::workspace()->activeWindow() : nullptr;\n            if (!active || isPanel(active)) {\n                if (waited < focusWaitMs) {\n                    m_pump.start(); // the panel is still going away: wait\n                    return;\n                }\n                if (active) {\n                    // focus never left the panel: typing now would go into its search box\n                    fail(m_jobs.takeFirst(), "kaomi.Caret.FocusOnPanel", "keyboard focus is on the panel");\n                } else {\n                    fail(m_jobs.takeFirst(), "kaomi.Caret.NoApp", "no app has keyboard focus");\n                }\n                continue;\n            }\n            if (!job.targetSet) {\n                job.target = active; // the app focus went to when the panel closed\n                job.targetSet = true;\n            }\n            if (job.target != active) {\n                fail(m_jobs.takeFirst(), "kaomi.Caret.FocusMoved", "you switched to another app");\n                continue;\n            }\n            if (!activeTextInput() && t - m_activatedAt < textInputWaitMs && waited < focusWaitMs + textInputWaitMs) {\n                m_pump.start(); // app just got focus: give it a moment to switch text input on\n                return;\n            }\n            const Job done = m_jobs.takeFirst();\n            type(done.text);\n            QDBusConnection::sessionBus().send(done.msg.createReply(true));\n        }\n    }\n\n    void type(const QString &text)\n    {\n        if (KWin::TextInputV3Interface *ti = activeTextInput()) {\n            ti->sendPreEditString(QString(), 0, 0); // same sequence KWin\'s own input method uses\n            ti->commitString(text);\n            ti->done();\n            return;\n        }\n        const auto ucs4 = text.toUcs4();\n        for (const char32_t cp : ucs4) {\n            if (const xkb_keysym_t sym = keysymFor(cp)) {\n                typeKeysym(sym);\n            }\n        }\n        if (auto *keyboard = KWin::input() ? KWin::input()->keyboard() : nullptr) {\n            keyboard->xkb()->forwardModifiers(); // the app hears your real modifiers again\n        }\n    }\n\n    static xkb_keysym_t keysymFor(char32_t cp)\n    {\n        if (cp == U\'\\n\') {\n            return XKB_KEY_Return;\n        }\n        if (cp == U\'\\t\') {\n            return XKB_KEY_Tab;\n        }\n        if (cp < 0x20 || (cp >= 0x7f && cp < 0xa0)) {\n            return XKB_KEY_NoSymbol; // other control characters: nothing to type\n        }\n        return xkb_utf32_to_keysym(cp); // the keysym your layout uses for it, if any\n    }\n\n    // One key press straight to the focused app (not through KWin\'s shortcuts\n    // or its keyboard state), like KWin\'s InputMethod::forwardKeySym. Modifiers\n    // are exactly what this character needs: a key you\'re holding or Caps Lock\n    // can\'t change it.\n    void typeKeysym(xkb_keysym_t sym)\n    {\n        auto *keyboard = KWin::input() ? KWin::input()->keyboard() : nullptr;\n        auto *xkb = keyboard ? keyboard->xkb() : nullptr;\n        auto *ws = KWin::waylandServer();\n        KWin::SeatInterface *seat = ws ? ws->seat() : nullptr;\n        if (!xkb || !seat || !seat->keyboard()) {\n            return;\n        }\n        if (const auto code = xkb->keycodeFromKeysym(sym)) {\n            // on your layout: that key, with Shift etc. as needed\n            seat->notifyKeyboardModifiers(code->modifiers, 0, 0, xkb->currentLayout());\n            seat->notifyKeyboardKey(code->keyCode, KWin::KeyboardKeyState::Pressed, ws->display()->nextSerial());\n            seat->notifyKeyboardKey(code->keyCode, KWin::KeyboardKeyState::Released, ws->display()->nextSerial());\n            return;\n        }\n        // not on your layout: a one-off keymap with just this character on F24,\n        // sent to the app, then your keymap again\n        static constexpr uint32_t keyF24 = 194;\n        const QByteArray oneOff = xkb->keymapContentsForKeysym(keyF24, sym);\n        if (oneOff.isEmpty()) {\n            return;\n        }\n        seat->keyboard()->setKeymap(oneOff);\n        seat->notifyKeyboardModifiers(0, 0, 0, 0);\n        seat->notifyKeyboardKey(keyF24, KWin::KeyboardKeyState::Pressed, ws->display()->nextSerial());\n        seat->notifyKeyboardKey(keyF24, KWin::KeyboardKeyState::Released, ws->display()->nextSerial());\n        seat->keyboard()->setKeymap(xkb->keymapContents());\n    }\n#endif\n\n    // Kaomi\'s panel windows (normally one), by pid and app id\n    QList<KWin::Window *> panels() const\n    {\n        QList<KWin::Window *> out;\n        if (m_pid <= 0 || !KWin::workspace()) {\n            return out;\n        }\n        for (KWin::Window *w : KWin::workspace()->windows()) {\n            if (!w->isDeleted() && w->pid() == m_pid && w->resourceClass() == QStringLiteral("kaomi")\n                && w->isShown() && !w->isMinimized() && w->isOnCurrentDesktop() && w->isOnCurrentActivity()) {\n                out.append(w);\n            }\n        }\n        return out;\n    }\n\n    void clicked(const QPointF &pos)\n    {\n        const auto ws = panels();\n        if (ws.isEmpty()) {\n            return;\n        }\n        for (KWin::Window *w : ws) {\n            if (w->frameGeometry().contains(pos)) {\n                return; // on the panel itself\n            }\n        }\n        Q_EMIT ClickedOutside(int(pos.x()), int(pos.y()));\n    }\n\n#if KAOMI_KWIN_VER >= 603\n    void pointerButton(KWin::PointerButtonEvent *event) override\n    {\n        if (event->state == KWin::PointerButtonState::Pressed) {\n            clicked(event->position);\n        }\n    }\n#else\n    void pointerEvent(KWin::MouseEvent *event) override\n    {\n        if (event->type() == QEvent::MouseButtonPress) {\n            clicked(event->globalPosition());\n        }\n    }\n#endif\n#if KAOMI_KWIN_VER >= 605\n    void touchDown(KWin::TouchDownEvent *event) override\n    {\n        clicked(event->pos);\n    }\n#else\n    void touchDown(qint32, const QPointF &pos, std::chrono::microseconds) override\n    {\n        clicked(pos);\n    }\n#endif\n\n    int m_pid = 0;\n    QString m_owner; // Kaomi\'s D-Bus connection (unique name)\n    QDBusServiceWatcher m_ownerWatch;\n    bool m_passive = false;\n#if KAOMI_KWIN_VER >= 606\n    QList<Job> m_jobs;\n    QTimer m_pump;\n    QElapsedTimer m_clock;\n    qint64 m_activatedAt = -1000000;\n#endif\n    KaomiEscapeFilter m_escape;\n};\n\nbool KaomiEscapeFilter::handle(bool pressed, bool repeat, bool withModifiers)\n{\n    if (pressed) {\n        if (withModifiers || !m_owner->panelOpen()) {\n            // Ctrl+Esc, Meta+Esc...: shortcuts, not ours\n            m_down = false;\n            return false; // panel closed: Escape is nobody\'s business but the app\'s\n        }\n        m_down = true;\n        if (!repeat) {\n            m_owner->escapePressed();\n        }\n        return true;\n    }\n    if (m_down) { // the release of a press we took\n        m_down = false;\n        return true;\n    }\n    return false;\n}\n\n#if KAOMI_KWIN_VER >= 603\nbool KaomiEscapeFilter::keyboardKey(KWin::KeyboardKeyEvent *event)\n{\n    if (event->key != Qt::Key_Escape) {\n        return false;\n    }\n    return handle(event->state != KWin::KeyboardKeyState::Released,\n                  event->state == KWin::KeyboardKeyState::Repeated,\n                  (event->modifiers & (Qt::ControlModifier | Qt::AltModifier | Qt::MetaModifier | Qt::ShiftModifier)) != 0);\n}\n\nbool KaomiEscapeFilter::pointerButton(KWin::PointerButtonEvent *event)\n{\n    return click(event->position, event->button, event->state == KWin::PointerButtonState::Pressed);\n}\n#else\nbool KaomiEscapeFilter::keyEvent(KWin::KeyEvent *event)\n{\n    if (event->key() != Qt::Key_Escape) {\n        return false;\n    }\n    return handle(event->type() == QEvent::KeyPress, event->isAutoRepeat(),\n                  (event->modifiers() & (Qt::ControlModifier | Qt::AltModifier | Qt::MetaModifier | Qt::ShiftModifier)) != 0);\n}\n\nbool KaomiEscapeFilter::pointerEvent(KWin::MouseEvent *event, quint32)\n{\n    if (event->type() != QEvent::MouseButtonPress && event->type() != QEvent::MouseButtonRelease) {\n        return false;\n    }\n    return click(event->globalPosition(), event->button(), event->type() == QEvent::MouseButtonPress);\n}\n#endif\n\nbool KaomiEscapeFilter::click(const QPointF &pos, Qt::MouseButton button, bool pressed)\n{\n    const int bit = int(button);\n    if (pressed) {\n        KWin::Window *w = m_owner->passivePanelAt(pos);\n        if (!w) {\n            m_clickDown &= ~bit; // (its release may have been eaten by the lock screen)\n            return false;        // not stay-open mode, or not on the panel: KWin as usual\n        }\n        m_clickDown |= bit;\n        m_owner->panelClicked(pos - w->frameGeometry().topLeft(), bit, true);\n        return true;\n    }\n    if (m_clickDown & bit) { // the release of a press we took\n        m_clickDown &= ~bit;\n        for (KWin::Window *w : m_owner->panelWindows()) {\n            m_owner->panelClicked(pos - w->frameGeometry().topLeft(), bit, false);\n            break;\n        }\n        return true;\n    }\n    return false;\n}\n\nclass KaomiCaretFactory : public KWin::PluginFactory\n{\n    Q_OBJECT\n    Q_PLUGIN_METADATA(IID PluginFactory_iid FILE "metadata.json")\n    Q_INTERFACES(KWin::PluginFactory)\n\npublic:\n    std::unique_ptr<KWin::Plugin> create() const override\n    {\n        return std::make_unique<KaomiCaret>();\n    }\n};\n\n#include "main.moc"\n',
    'metadata.json': '{\n    "KPlugin": {\n        "Id": "kaomi_caret",\n        "Name": "Kaomi text cursor",\n        "Description": "Lets Kaomi open at the text cursor",\n        "EnabledByDefault": false\n    }\n}\n',
    'CMakeLists.txt': 'cmake_minimum_required(VERSION 3.16)\nproject(kaomi_caret LANGUAGES CXX)\nset(CMAKE_CXX_STANDARD 23)\nset(CMAKE_CXX_STANDARD_REQUIRED OFF)\nset(CMAKE_AUTOMOC ON)\nfind_package(ECM REQUIRED NO_MODULE)\nlist(APPEND CMAKE_MODULE_PATH ${ECM_MODULE_PATH})\n# KWin links Qt Widgets/Quick/DBus publicly but only loads Core/Gui/Quick itself\nfind_package(Qt6 REQUIRED COMPONENTS Core Gui Widgets DBus Quick)\nfind_package(KWin REQUIRED)\n# libkwin uses xkbcommon privately; the typing code calls it directly\nfind_package(PkgConfig REQUIRED)\npkg_check_modules(XKB REQUIRED IMPORTED_TARGET xkbcommon)\n# KWin\'s input-spy API changed shape in 6.3 and 6.5: tell the source which one it gets\nstring(REPLACE "." ";" _kwin_ver "${KWin_VERSION}")\nlist(GET _kwin_ver 0 _kwin_major)\nlist(GET _kwin_ver 1 _kwin_minor)\nmath(EXPR KAOMI_KWIN_VER "${_kwin_major} * 100 + ${_kwin_minor}")\nmessage(STATUS "Building for KWin ${KWin_VERSION} (api ${KAOMI_KWIN_VER})")\nadd_library(kaomi_caret MODULE main.cpp)\nset_target_properties(kaomi_caret PROPERTIES PREFIX "")\ntarget_compile_definitions(kaomi_caret PRIVATE KAOMI_KWIN_VER=${KAOMI_KWIN_VER})\ntarget_link_libraries(kaomi_caret PRIVATE KWin::kwin Qt6::Core Qt6::DBus PkgConfig::XKB)\n',
}
KPLUG_BUILD = r"""
set -e
SRC="$1"; BLD="$2"
rm -rf "$BLD"
cmake -S "$SRC" -B "$BLD" -DCMAKE_BUILD_TYPE=Release
cmake --build "$BLD" -j"$(nproc)"
"""


# Everything KWin's CMake package and headers pull in (Ubuntu's kwin-dev misses some)
KPLUG_DEPS = ["kwin-dev", "cmake", "g++", "extra-cmake-modules", "qt6-base-dev", "qt6-declarative-dev",
              "libkf6config-dev", "libkf6coreaddons-dev", "libkf6windowsystem-dev", "libwayland-dev",
              "libepoxy-dev", "libdrm-dev", "libvulkan-dev", "libxcb1-dev", "libxkbcommon-dev", "pkg-config", "make"]


def kplug_missing_deps():
    import subprocess
    missing = []
    for pkg in KPLUG_DEPS:
        r = subprocess.run(["dpkg-query", "-W", "-f=${Status}", pkg], capture_output=True, text=True)
        if "install ok installed" not in r.stdout:
            missing.append(pkg)
    return missing


def kplug_system_dir():
    """KWin's plugin folder, from Qt itself (falls back to the usual Debian paths)."""
    import subprocess, sysconfig
    base = None
    for cmd in (["qtpaths6", "--query", "QT_INSTALL_PLUGINS"], ["qmake6", "-query", "QT_INSTALL_PLUGINS"]):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout.strip()
            if out and os.path.isdir(out):
                base = out
                break
        except Exception:
            pass
    if base is None:
        arch = sysconfig.get_config_var("MULTIARCH") or "x86_64-linux-gnu"
        for c in (f"/usr/lib/{arch}/qt6/plugins", "/usr/lib64/qt6/plugins", "/usr/lib/qt6/plugins"):
            if os.path.isdir(c):
                base = c
                break
    return os.path.join(base, "kwin", "plugins") if base else None


def kplug_system_file():
    d = kplug_system_dir()
    return os.path.join(d, KPLUG_ID + ".so") if d else None


def installed_kwin_version():
    import re, subprocess
    try:
        out = subprocess.run(["kwin_wayland", "--version"], capture_output=True, text=True, timeout=5).stdout
        m = re.search(r"(\d+\.\d+\.\d+)", out)
        return m.group(1) if m else None
    except Exception:
        return None


def kplug_source_hash():
    import hashlib as _h
    return _h.sha1("".join(KPLUG_FILES[k] for k in sorted(KPLUG_FILES)).encode()).hexdigest()[:12]


def pkg_version(*names):
    """Exact Ubuntu package version of the first installed package (or None)."""
    import subprocess
    for n in names:
        try:
            r = subprocess.run(["dpkg-query", "-W", "-f=${Status} ${Version}", n],
                               capture_output=True, text=True, timeout=5)
            if r.stdout.startswith("install ok installed"):
                return r.stdout.split()[-1]
        except Exception:
            return None
    return None


def kwin_runtime_version():
    # the exact package version catches Ubuntu patch releases too
    return pkg_version("kwin-wayland", "kwin-common") or installed_kwin_version()


def kplug_wanted_stamp():
    v = kwin_runtime_version()
    return f"{v} {kplug_source_hash()}" if v else None


def running_kwin_is_old():
    """True if KWin was updated on disk but the running one is still the old
    version (you haven't logged out yet)."""
    import subprocess
    try:
        pid = subprocess.run(["pgrep", "-u", str(os.getuid()), "-x", "kwin_wayland"],
                             capture_output=True, text=True, timeout=5).stdout.split()[0]
        return os.readlink(f"/proc/{pid}/exe").endswith(" (deleted)")
    except Exception:
        return False


def kplug_running_api():
    """Api level of the plugin KWin is running right now: 0 = not loaded,
    1 = an older build (no Api method), else the number it reports."""
    import subprocess
    call = ["busctl", "--user", "call", "org.kde.KWin", "/KaomiCaret", "kaomi.Caret"]
    r = subprocess.run(call + ["Api"], capture_output=True, text=True)
    if r.returncode == 0:
        try:
            return int(r.stdout.split()[-1])
        except (ValueError, IndexError):
            return 1
    if subprocess.run(call + ["BuiltFor"], capture_output=True).returncode == 0:
        return 1
    return 0


def kplug_prepare():
    src = os.path.join(KPLUG_DIR, "src")
    os.makedirs(src, exist_ok=True)
    for name, text in KPLUG_FILES.items():
        with open(os.path.join(src, name), "w") as f:
            f.write(text)
    return src, os.path.join(KPLUG_DIR, "build")


def kplug_update():
    """Build the plugin, install it as a root-owned system file, and load it.
    Used by the installer and by the notification's "Update now" button."""
    import subprocess, shutil
    print("Updating Kaomi's text-cursor plugin for KWin...\n")
    stamp = kplug_wanted_stamp()
    dest_dir = kplug_system_dir()
    if not stamp or not dest_dir:
        print("KWin wasn't found, nothing to do."); return 1
    missing = kplug_missing_deps() if shutil.which("dpkg-query") else []
    if missing:
        print("Installing build tools it needs (asks for your password):", " ".join(missing))
        r = subprocess.run(["sudo", "apt-get", "install", "-y", "-qq", "--no-install-recommends"] + missing,
                           stdout=subprocess.DEVNULL)
        if r.returncode != 0:
            print("Couldn't install:", " ".join(missing)); return 1
    dev, run = pkg_version("kwin-dev"), pkg_version("kwin-wayland", "kwin-common")
    if dev and run and dev != run:
        print(f"KWin's build files (kwin-dev {dev}) don't match KWin itself ({run}).")
        print("Run:  sudo apt update && sudo apt upgrade   then try again.")
        return 1
    print("Building (takes about 30 seconds)...")
    src, bld = kplug_prepare()
    r = subprocess.run(["bash", "-c", KPLUG_BUILD, "build", src, bld],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if r.returncode != 0:
        lines = r.stdout.splitlines()
        important = []
        for i, l in enumerate(lines):          # each error plus the lines explaining it
            if "rror" in l or "Could NOT find" in l:
                important += [x for x in lines[i:i + 6] if x.strip()] + [""]
        print("\n".join((important or lines)[-24:]))
        with open(os.path.join(KPLUG_DIR, "last-build.log"), "w") as f:
            f.write(r.stdout)
        print("\nBuilding failed. Full log:", os.path.join(KPLUG_DIR, "last-build.log"))
        return 1
    built = os.path.join(bld, KPLUG_ID + ".so")
    dest = os.path.join(dest_dir, KPLUG_ID + ".so")
    print("Installing it into", dest_dir, "(asks for your password)")
    import hashlib as _h
    with open(built, "rb") as f:
        digest = _h.sha256(f.read()).hexdigest()
    # root checks it installs exactly the file just built (nothing swapped in
    # meanwhile); install next to it, then rename: never overwrite a file KWin has loaded
    r = subprocess.run(["sudo", "sh", "-c",
                        'echo "$3  $1" | sha256sum -c --quiet && '
                        'install -m 644 -o root -g root "$1" "$2.new" && mv -f "$2.new" "$2"',
                        "x", built, dest, digest])
    if r.returncode != 0:
        print("Installing failed."); return 1
    with open(KPLUG_STAMP, "w") as f:
        f.write(stamp)
    subprocess.run(["busctl", "--user", "call", "org.kde.KWin", "/Plugins",
                    "org.kde.KWin.Plugins", "LoadPlugin", "s", KPLUG_ID],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    api = kplug_running_api()
    # tell the running picker to re-check (closes its notification)
    try:
        c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); c.settimeout(1)
        c.connect(SOCK); c.sendall(b"kplug-check\n"); c.close()
    except OSError:
        pass
    if api >= KPLUG_API:
        print("\nDone! The plugin is active.")
    elif api > 0:
        # KWin can't swap a plugin it has already loaded; the file is in place
        print("\nInstalled. Plasma is still running the previous version of the plugin;")
        print("the new one takes over after you log out and back in.")
    elif running_kwin_is_old():
        print("\nInstalled. Plasma was updated, so it turns on after you log out and back in.")
    else:
        print("\nInstalled. It turns on the next time you log in.")
    return 0


if "--kplug-status" in sys.argv:       # used by the installer's final report
    api = kplug_running_api()
    print("active" if api >= KPLUG_API else "outdated" if api > 0 else "off"); sys.exit(0)

if "--update-kwin-plugin" in sys.argv or "--build-kwin-plugin" in sys.argv:
    sys.exit(kplug_update())


# ---------------------------------------------------------------- full app --
import json, zlib, base64, time, math, re
from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF, QEvent, QSize, QByteArray, QPoint, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import (QPainter, QColor, QFont, QPainterPath, QGuiApplication,
                         QClipboard, QPen, QFontMetrics, QAction, QIcon, QPixmap)
from PyQt6.QtCore import QMimeData, QObject, pyqtSignal, pyqtSlot, QProcess
import hashlib, shutil, uuid
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLineEdit, QScrollArea, QToolButton, QLabel, QMenu,
                             QButtonGroup, QFrame, QStackedWidget, QCheckBox,
                             QRadioButton, QPushButton, QSizePolicy)
from PyQt6.QtNetwork import QLocalServer
from PyQt6.QtSvg import QSvgRenderer

CONF_DIR = os.path.join(os.path.expanduser("~"), ".config", APP_ID)
CONF_FILE = os.path.join(CONF_DIR, "settings.json")
DATA_DIR = os.path.join(os.path.expanduser("~"), ".local", "share", APP_ID)
DEFAULT_CONF = {
    "close_on_mouse": True,      # close after clicking an emoji/item
    "close_on_keyboard": True,   # close after choosing with Enter
    "paste_keys": "shift+insert",  # "shift+insert" | "ctrl+v" | "none"
    "paste_delay_ms": 35,
    "skin_tone": 0,
    "recent": [],
    "clipboard_history": True,
    "type_emoji": True,          # type emoji as keystrokes instead of pasting (Plasma 6.6+)
    "placement": "caret",        # "caret" | "mouse" | "window" | "center" | "remember"
}
CLIP_MAX = 200                      # items kept (Windows keeps 25)
CLIP_IMAGE_BUDGET = 200 * 1024 * 1024   # images in history beyond this: oldest dropped
RECENT_ROWS = 3                     # "Recently used" emoji rows shown
CLIP_TEXT_MAX = 2 * 1024 * 1024
CLIP_IMAGE_MAX = 25 * 1024 * 1024
CLIP_RESTORE_MAX = 64 * 1024 * 1024   # too big for history, but still put back after an insert
PIN_DIR = os.path.join(os.path.expanduser("~"), ".local", "share", APP_ID, "pinned")
EMOJI_FONT = "Noto Color Emoji"
CELL = 44
EMOJI_PX = 26
COLS_MIN = 7
TONES = ["", "\U0001F3FB", "\U0001F3FC", "\U0001F3FD", "\U0001F3FE", "\U0001F3FF"]
TONE_NAMES = ["Default", "Light", "Medium-light", "Medium", "Medium-dark", "Dark"]
TONE_COLORS = ["#FFC83D", "#F7DECE", "#F3D2A2", "#D5AB88", "#AF7E57", "#7C533E"]
PERSON = set("\U0001F468\U0001F469\U0001F9D1\U0001F466\U0001F467\U0001F9D2")


# ----------------------------------------------------------------- icons ---
def _gear():
    spokes = "".join(
        f'<path d="M{12 + 6.2 * math.cos(a):.2f} {12 + 6.2 * math.sin(a):.2f}'
        f'L{12 + 8.6 * math.cos(a):.2f} {12 + 8.6 * math.sin(a):.2f}" stroke-width="2.4"/>'
        for a in [i * math.pi / 4 for i in range(8)])
    return f'<circle cx="12" cy="12" r="2.6"/><circle cx="12" cy="12" r="6.2"/>{spokes}'


SVG = {
    "recent": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    "smileys": '<circle cx="12" cy="12" r="8.5"/><circle cx="9" cy="10" r="1" fill="C" stroke="none"/>'
               '<circle cx="15" cy="10" r="1" fill="C" stroke="none"/>'
               '<path d="M8.5 14.3c.9 1.4 2.1 2.1 3.5 2.1s2.6-.7 3.5-2.1"/>',
    "people": '<circle cx="12" cy="8" r="3.6"/><path d="M5 20c0-3.7 3.1-6.2 7-6.2s7 2.5 7 6.2"/>',
    "animals": '<path d="M12 12.3c-2.7 0-5.1 2.5-5.1 4.7 0 1.6 1.2 2.5 2.6 2.5 1 0 1.6-.5 2.5-.5s1.5.5 2.5.5'
               'c1.4 0 2.6-.9 2.6-2.5 0-2.2-2.4-4.7-5.1-4.7z"/><ellipse cx="6.3" cy="10.2" rx="1.5" ry="2"/>'
               '<ellipse cx="9.8" cy="6.4" rx="1.5" ry="2.1"/><ellipse cx="14.2" cy="6.4" rx="1.5" ry="2.1"/>'
               '<ellipse cx="17.7" cy="10.2" rx="1.5" ry="2"/>',
    "food": '<path d="M4.5 9.5h11.5v4.2a5.3 5.3 0 0 1-5.3 5.3h-.9a5.3 5.3 0 0 1-5.3-5.3z"/>'
            '<path d="M16 10.8h1.4a2.4 2.4 0 0 1 0 4.8H16"/><path d="M8.5 3.8v2.7M12 3.8v2.7"/>',
    "travel": '<path d="M3.8 16.2v-3.9l1.8-4.5A2 2 0 0 1 7.5 6.5h9a2 2 0 0 1 1.9 1.3l1.8 4.5v3.9z"/>'
              '<path d="M3.8 12.3h16.4"/><circle cx="7.6" cy="18" r="1.6"/><circle cx="16.4" cy="18" r="1.6"/>',
    "activities": '<path d="M8 4.5h8v4.8a4 4 0 0 1-8 0z"/><path d="M8 6.2H5.6a2.6 2.6 0 0 0 2.7 3.6'
                  'M16 6.2h2.4a2.6 2.6 0 0 1-2.7 3.6"/><path d="M12 13.3v3.2M8.5 20h7M9.8 20l.5-3.5h3.4l.5 3.5"/>',
    "objects": '<path d="M9.3 17.2h5.4M10.2 20.2h3.6"/><path d="M12 3.5a5.6 5.6 0 0 0-3.3 10.1'
               'c.6.5 1 1.1 1 1.8v1.8h4.6v-1.8c0-.7.4-1.3 1-1.8A5.6 5.6 0 0 0 12 3.5z"/>',
    "flags": '<path d="M5.5 21V3.8"/><path d="M5.5 4.5h11.2l-2.3 4.1 2.3 4.1H5.5"/>',
    "settings": _gear(),
    "back": '<path d="M19.5 12h-15M10.5 6l-6 6 6 6"/>',
    "search": '<circle cx="10.5" cy="10.5" r="6.2"/><path d="M15.2 15.2l5 5"/>',
    "close": '<path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/>',
    "kaomoji": '<text x="12" y="16.5" font-size="13" font-weight="700" text-anchor="middle" '
               'fill="C" stroke="none" font-family="sans-serif">;-)</text>',
    "symbols": '<text x="12" y="18.5" font-size="19" text-anchor="middle" fill="C" stroke="none" '
               'font-family="serif">Ω</text>',
    "clipboard": '<rect x="5.5" y="4.8" width="13" height="16" rx="2"/><rect x="9" y="3.2" width="6" height="3.2" rx="1"/>'
                 '<path d="M9 11h6M9 14h6M9 17h3.5"/>',
    "more": '<circle cx="6" cy="12" r="1.3" fill="C" stroke="none"/><circle cx="12" cy="12" r="1.3" fill="C" stroke="none"/>'
            '<circle cx="18" cy="12" r="1.3" fill="C" stroke="none"/>',
    "pin": '<path d="M9.3 3.8h5.4l-.9 5.1 3.2 3.1v1.6H7v-1.6l3.2-3.1z"/><path d="M12 13.6v6.6"/>',
    "pinned": '<path d="M9.3 3.8h5.4l-.9 5.1 3.2 3.1v1.6H7v-1.6l3.2-3.1z" fill="C"/><path d="M12 13.6v6.6"/>',
    "delete": '<path d="M5 7h14M10 7V4.8h4V7M7 7l1 13h8l1-13"/>',
    "pastetext": '<rect x="5.5" y="4.8" width="13" height="16" rx="2"/><rect x="9" y="3.2" width="6" height="3.2" rx="1"/>'
                 '<path d="M9.3 17.2l2.7-7 2.7 7M10.3 14.8h3.4"/>',
}
TAB_KEYS = ["recent", "smileys", "people", "animals", "food", "travel",
            "activities", "objects", "symbols", "flags"]


_ICON_CACHE = {}


def svg_icon(name, color, px=20):
    dpr = max(1.0, QGuiApplication.instance().devicePixelRatio())
    scale = max(2, math.ceil(dpr))
    key = (name, color, px, scale)
    if key not in _ICON_CACHE:             # every clipboard row uses the same few icons
        _ICON_CACHE[key] = _render_svg_icon(name, color, px, scale)
    return _ICON_CACHE[key]


def _render_svg_icon(name, color, px, scale):
    body = SVG[name].replace('"C"', f'"{color}"')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
           f'stroke="{color}" stroke-width="1.6" stroke-linecap="round" '
           f'stroke-linejoin="round">{body}</svg>')
    pm = QPixmap(px * scale, px * scale)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    QSvgRenderer(QByteArray(svg.encode())).render(p)
    p.end()
    pm.setDevicePixelRatio(scale)
    return QIcon(pm)


def swatch_icon(color, px=18, ring=None):
    scale = 2
    pm = QPixmap(px * scale, px * scale)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm); p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(QPen(QColor(ring or "#00000040"), 1.2 * scale))
    p.drawEllipse(QRectF(2 * scale, 2 * scale, (px - 4) * scale, (px - 4) * scale))
    p.end()
    pm.setDevicePixelRatio(scale)
    return QIcon(pm)


LOG_FILE = os.path.join(os.path.expanduser("~"), ".cache", APP_ID + ".log")


def _open_log():
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    fd = os.open(LOG_FILE, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    return os.fdopen(fd, "a", buffering=1)


def rotate_log():
    """Once, at startup (stderr is redirected into the log, so not while running)."""
    try:
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > 512 * 1024:
            os.replace(LOG_FILE, LOG_FILE + ".old")
    except Exception:
        pass


LOG_MAX = 512 * 1024      # while running, the log is trimmed to its newest part past this
LOG_KEEP = 128 * 1024


def _trim_log():
    """Keep only the newest part of the log, in place. Everything writing to it
    (log() and stderr) appends, so their next line just lands at the new end."""
    with open(LOG_FILE, "r+b") as f:
        f.seek(-LOG_KEEP, os.SEEK_END)
        tail = f.read()
        tail = tail[tail.find(b"\n") + 1:]               # start at a whole line
        f.seek(0)
        f.truncate()
        f.write(b"(older lines trimmed)\n" + tail)


def log(msg):
    try:
        with _open_log() as f:
            if os.fstat(f.fileno()).st_size > LOG_MAX:
                _trim_log()
            f.write(time.strftime("%H:%M:%S ") + msg + "\n")
    except Exception:
        pass


# ---------------------------------------------------------------- config ---
def load_conf():
    c = dict(DEFAULT_CONF)
    raw = {}
    try:
        with open(CONF_FILE) as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            raw = {}
        c.update(raw)
    except Exception:
        raw = {}
    if "close_on_mouse" not in raw and "close_after_pick" in raw:   # older settings format
        on = raw.get("close_on", "both")
        c["close_on_mouse"] = bool(raw["close_after_pick"]) and on in ("both", "mouse")
        c["close_on_keyboard"] = bool(raw["close_after_pick"]) and on in ("both", "keyboard")
    for k in ("close_after_pick", "close_on"):
        c.pop(k, None)
    if c.get("paste_delay_ms") == 140:      # old default, far slower than needed
        c["paste_delay_ms"] = DEFAULT_CONF["paste_delay_ms"]
    return validate_conf(c)


CONF_CHOICES = {
    "paste_keys": ("shift+insert", "ctrl+v", "none"),
    "placement": ("caret", "mouse", "window", "center", "remember"),
}


def validate_conf(c):
    """A hand-edited or damaged settings file must never crash the picker:
    every value that has the wrong type or an unknown choice goes back to default."""
    out = dict(DEFAULT_CONF)
    for k, default in DEFAULT_CONF.items():
        v = c.get(k, default)
        if k in CONF_CHOICES:
            ok = v in CONF_CHOICES[k]
        elif isinstance(default, bool):
            ok = isinstance(v, bool)
        elif k == "skin_tone":
            ok = isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 5
        elif k == "paste_delay_ms":
            ok = isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 1000
        elif isinstance(default, list):
            ok = isinstance(v, list)
            if ok:
                v = [x for x in v if isinstance(x, str)]
        else:
            ok = isinstance(v, type(default))
        out[k] = v if ok else default
    for k in ("recent_kaomoji", "recent_symbols"):   # optional lists
        v = c.get(k, [])
        out[k] = [x for x in v if isinstance(x, str)] if isinstance(v, list) else []
    return out


def save_conf(c):
    try:
        os.makedirs(CONF_DIR, exist_ok=True)
        tmp = CONF_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(c, f, ensure_ascii=False, indent=1)
        os.replace(tmp, CONF_FILE)
    except Exception:
        pass


def apply_tone(emoji, tone):
    if not tone:
        return emoji
    mod = TONES[tone]
    parts = emoji.split("‍")
    out = []
    for i, p in enumerate(parts):
        if p and (i == 0 or p[0] in PERSON):
            rest = p[1:]
            if rest.startswith("️"):
                rest = rest[1:]
            p = p[0] + mod + rest
        out.append(p)
    return "‍".join(out)


# ------------------------------------------------------------ virtual keys --
# ---------------------------------------------------------- auto-insert ----
# Pressing the paste keys goes through KDE's official remote-input permission
# (the desktop portal). KDE asks once ("allow ... to control input devices"),
# remembers the answer, and shows a small notice when a session starts (once
# per login). No special system access is needed and no other program gains
# the ability to type.
KEYS_HELPER = r"""
# kaomi-keys-helper
import os, sys
import gi
gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

TOKEN_FILE = sys.argv[1]
BUS, PATH = "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop"
RD = "org.freedesktop.portal.RemoteDesktop"
KEYS = {"shift+insert": (42, 110), "ctrl+v": (29, 47)}   # evdev key codes

bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
loop = GLib.MainLoop()
n = [0]


def say(msg):
    print(msg, flush=True)


def request(method, params_fmt, args, timeout_s=300):
    n[0] += 1
    token = f"kaomi{os.getpid()}_{n[0]}"
    sender = bus.get_unique_name()[1:].replace(".", "_")
    path = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"
    out = {}

    def on_response(_c, _s, _p, _i, _sig, params):
        out["code"], out["res"] = params.unpack()
        loop.quit()
    sub = bus.signal_subscribe(BUS, "org.freedesktop.portal.Request", "Response", path, None,
                               Gio.DBusSignalFlags.NO_MATCH_RULE, on_response)
    args[-1]["handle_token"] = GLib.Variant("s", token)
    bus.call_sync(BUS, PATH, RD, method, GLib.Variant(params_fmt, tuple(args)), None,
                  Gio.DBusCallFlags.NONE, timeout_s * 1000, None)
    GLib.timeout_add_seconds(timeout_s, loop.quit)
    loop.run()
    bus.signal_unsubscribe(sub)
    return out.get("code", -1), out.get("res", {})


def main():
    # tell the portal who we are, so the remembered permission belongs to the
    # picker however it was started (login, terminal, ...)
    try:
        bus.call_sync(BUS, PATH, "org.freedesktop.host.portal.Registry", "Register",
                      GLib.Variant("(sa{sv})", ("kaomi", {})), None,
                      Gio.DBusCallFlags.NONE, 5000, None)
    except GLib.Error:
        pass
    try:
        version = bus.call_sync(BUS, PATH, "org.freedesktop.DBus.Properties", "Get",
                                GLib.Variant("(ss)", (RD, "version")), None,
                                Gio.DBusCallFlags.NONE, 5000, None).unpack()[0]
    except GLib.Error as e:
        say("error: KDE's remote-input portal isn't available (" + e.message + ")")
        return 2
    saved = None
    try:
        saved = open(TOKEN_FILE).read().strip() or None
    except OSError:
        pass
    code, res = request("CreateSession", "(a{sv})",
                        [{"session_handle_token": GLib.Variant("s", f"kaomisess{os.getpid()}")}])
    if code != 0:
        say("error: couldn't start a session"); return 2
    session = res["session_handle"]
    opts = {"types": GLib.Variant("u", 1)}                  # keyboard only
    if version >= 2:
        opts["persist_mode"] = GLib.Variant("u", 2)         # remember until revoked
        if saved:
            opts["restore_token"] = GLib.Variant("s", saved)
    code, _ = request("SelectDevices", "(oa{sv})", [session, opts])
    if code != 0:
        say("error: couldn't select the keyboard"); return 2
    code, res = request("Start", "(osa{sv})", [session, "", {}])
    if code == 1:
        say("denied"); return 1
    if code != 0:
        say("error: permission request failed"); return 2
    tok = res.get("restore_token")
    if tok:
        os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
        fd = os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(tok)
    say("ready")
    for line in sys.stdin:                 # one line per paste; ends when the picker exits
        line = line.strip()
        keys = KEYS.get(line)
        if not keys:
            continue
        mod, key = keys
        try:
            for code_, state in ((mod, 1), (key, 1), (key, 0), (mod, 0)):
                bus.call_sync(BUS, PATH, RD, "NotifyKeyboardKeycode",
                              GLib.Variant("(oa{sv}iu)", (session, {}, code_, state)),
                              None, Gio.DBusCallFlags.NONE, 2000, None)
        except GLib.Error as e:
            say("error: session ended (" + e.message + ")"); return 3
    return 0


sys.exit(main())
"""


class Paster(QObject):
    """Presses Shift+Insert / Ctrl+V through KDE's remote-input permission."""

    def __init__(self):
        super().__init__()
        self.ui = None            # set once the permission is granted and a session is open
        self.error = None
        self.denied = False
        self.proc = None
        self.restarts = 0
        self.token_file = os.path.join(DATA_DIR, "portal-token")
        self.retry = QTimer(self); self.retry.setSingleShot(True); self.retry.setInterval(3000)
        self.retry.timeout.connect(self.start)
        self.start()

    def start(self):
        if self.proc is not None or os.environ.get("KAOMI_NO_KEYS_HELPER"):   # (tests)
            return
        self.error = "starting…"
        self.proc = QProcess(self)
        self.proc.setProgram(os.environ.get("KAOMI_HELPER_PYTHON", sys.executable))
        self.proc.setArguments(["-c", KEYS_HELPER, self.token_file])
        self.proc.readyReadStandardOutput.connect(self._read)
        self.proc.readyReadStandardError.connect(self._stderr)
        self.proc.finished.connect(self._died)
        self.proc.errorOccurred.connect(lambda e: e == QProcess.ProcessError.FailedToStart and self._died())
        self.proc.start()

    def _stderr(self):
        try:
            log("keys helper: " + bytes(self.proc.readAllStandardError()).decode(errors="ignore").strip()[-300:])
        except (RuntimeError, AttributeError):
            pass

    def _read(self):
        for line in bytes(self.proc.readAllStandardOutput()).decode(errors="ignore").splitlines():
            if line == "ready":
                self.ui, self.error, self.restarts = True, None, 0
                log("auto-insert: ready (KDE remote-input permission)")
            elif line == "denied":
                self.denied, self.ui = True, None
                self.error = "you declined KDE's permission to control input"
                log("auto-insert: permission declined")
            elif line.startswith("error:"):
                self.ui, self.error = None, line[6:].strip()
                log("auto-insert: " + self.error)


    def _died(self, *_):
        if self.proc is None:
            return
        self.proc.deleteLater(); self.proc = None
        self.ui = None
        if self.denied:
            return                               # never nag; Settings has "Ask again"
        self.restarts += 1
        if self.restarts <= 5:
            self.retry.start()

    def ask_again(self):
        self.denied, self.restarts = False, 0
        self.start()

    def paste(self, combo):
        if self.ui and self.proc is not None and combo != "none":
            self.proc.write(f"{combo}\n".encode())
        elif self.proc is None and not self.denied:
            self.restarts = 0                    # the helper gave up earlier: try once more
            self.start()


# ---------------------------------------------------------- text cursor ----
# Apps tell the accessibility system (AT-SPI, what screen readers use) where
# their text cursor is. A small helper process listens for that and reports
# "pid x y height" (relative to the app window) so the panel can open right
# above the text cursor, like on Windows.
CARET_HELPER = r"""
# kaomi-caret-helper
import sys, os, subprocess, threading
OWN = int(sys.argv[1]) if len(sys.argv) > 1 else -1     # the picker itself: ignore it
def watch_parent():
    sys.stdin.read()          # returns when the picker exits (pipe closes)
    os._exit(0)
threading.Thread(target=watch_parent, daemon=True).start()
subprocess.run(["busctl", "--user", "set-property", "org.a11y.Bus", "/org/a11y/bus",
                "org.a11y.Status", "IsEnabled", "b", "true"],
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
import gi
gi.require_version("Atspi", "2.0")
from gi.repository import Atspi
Atspi.init()
WIN = Atspi.CoordType.WINDOW
def report(acc):
    t = acc.get_text_iface()
    if t is None:
        return
    off = t.get_caret_offset()
    if off < 0:
        return
    r = t.get_character_extents(off, WIN)
    if r.height <= 0 and off > 0:                  # caret at end of text
        p = t.get_character_extents(off - 1, WIN)
        r.x, r.y, r.height = p.x + p.width, p.y, p.height
    if r.height <= 0:
        e = acc.get_component_iface()
        if e is None:
            return
        r = e.get_extents(WIN)
        r.x, r.height = r.x + 4, min(r.height, 24)
    pid = acc.get_process_id()
    if pid == OWN:
        return
    print(pid, r.x, r.y, r.height, flush=True)
def on_event(ev):
    try:
        if ev.type.startswith("object:state-changed") and not ev.detail1:
            return
        report(ev.source)
    except Exception:
        pass
l = Atspi.EventListener.new(on_event)
l.register("object:text-caret-moved")
l.register("object:state-changed:focused")
print("ready", flush=True)
Atspi.event_main()
"""


class CaretTracker(QObject):
    def __init__(self):
        super().__init__()
        self.last = None      # (pid, x, y, h) most recent, for the log
        self.by_pid = {}      # pid -> (x, y, h), most recent last
        self.ready = False
        self.proc = QProcess(self)
        self.proc.setProgram(sys.executable)
        self.proc.setArguments(["-c", CARET_HELPER, str(os.getpid())])
        self.proc.readyReadStandardOutput.connect(self._read)
        self.proc.readyReadStandardError.connect(self._stderr)
        self.proc.start()

    def _stderr(self):
        try:
            log("caret helper: " + bytes(self.proc.readAllStandardError()).decode(errors="ignore").strip()[-300:])
        except RuntimeError:
            pass                  # process object already gone (app shutting down)

    def _read(self):
        for line in bytes(self.proc.readAllStandardOutput()).decode(errors="ignore").splitlines():
            if line == "ready":
                self.ready = True; log("text cursor tracking ready"); continue
            try:
                pid, x, y, h = (int(v) for v in line.split())
                if pid == os.getpid():
                    continue
                self.last = (pid, x, y, h)
                self.by_pid.pop(pid, None)
                self.by_pid[pid] = (x, y, h)
                while len(self.by_pid) > 6:
                    self.by_pid.pop(next(iter(self.by_pid)))
            except ValueError:
                pass


class KwinCaretPlugin(QObject):
    """Keeps the KWin text-cursor plugin built and loaded, and asks it for the cursor."""
    activeChanged = pyqtSignal(bool)
    clickedOutside = pyqtSignal(int, int)    # a click/tap not on the panel, while it is open
    escapePressed = pyqtSignal()             # Escape while the panel is open, wherever focus is
    panelClicked = pyqtSignal(int, int, int, bool)   # stay-open mode: x, y, button, pressed

    def __init__(self):
        super().__init__()
        self.active = False
        self.clicks = False        # plugin can report clicks outside the panel (api >= 2)
        self.api = 0
        self.can_commit = False    # plugin can commit text like an input method (api >= 7)
        self._notif_id = None
        self._listening = False
        from PyQt6.QtDBus import QDBusConnection
        self.bus = QDBusConnection.sessionBus()
        self.bus.connect("org.kde.KWin", "/KaomiCaret", "kaomi.Caret", "ClickedOutside", self._clicked)
        self.bus.connect("org.kde.KWin", "/KaomiCaret", "kaomi.Caret", "EscapePressed", self._escape)
        self.bus.connect("org.kde.KWin", "/KaomiCaret", "kaomi.Caret", "PanelClicked", self._panel_click)

    @pyqtSlot(int, int)
    def _clicked(self, x, y):
        self.clickedOutside.emit(x, y)

    @pyqtSlot()
    def _escape(self):
        self.escapePressed.emit()

    @pyqtSlot(int, int, int, bool)
    def _panel_click(self, x, y, button, pressed):
        self.panelClicked.emit(x, y, button, pressed)

    def type_text(self, text, failed, done):
        """Ask the KWin plugin to type `text` into the focused app (api >= 7). The
        plugin waits until focus has left the panel, so this may be called right
        after hiding it. `done()` runs once the text is in the app's hands;
        `failed()` runs instead if the plugin can't type, so the caller can paste."""
        try:
            from PyQt6.QtDBus import QDBusConnection, QDBusMessage
            msg = QDBusMessage.createMethodCall("org.kde.KWin", "/KaomiCaret", "kaomi.Caret", "TypeText")
            msg.setArguments([text])

            def ok(reply_ok):
                if reply_ok:
                    done()
                else:
                    log("typing: KWin plugin refused; pasting instead")
                    failed()

            def err(message):
                gone = ("org.freedesktop.DBus.Error.ServiceUnknown", "org.freedesktop.DBus.Error.UnknownObject",
                        "org.freedesktop.DBus.Error.UnknownMethod")
                if message.startswith(gone):
                    log("typing: KWin plugin not there (" + message + "); pasting instead")
                    failed()
                    return
                # The plugin decided not to type it (focus stayed on the panel, you
                # switched apps, screen locked...), or it didn't answer in time and
                # may still type it: pasting now could put it in twice or in the
                # wrong place. A lost pick is better than either.
                log("typing: nothing typed (" + message + ")")
                done()
            r = DBusBoolReply(self, ok, err)
            if not self.bus.callWithCallback(msg, r.ok, r.err, 2000):
                failed()
        except Exception as ex:
            log(f"typing: {ex}; pasting instead")
            failed()

    def set_passive(self, on):
        """Stay-open mode: ask the plugin to take clicks on the panel (so KWin
        doesn't move keyboard focus to it) and hand them to us."""
        if self.api < 5:
            return
        try:
            from PyQt6.QtDBus import QDBusMessage
            msg = QDBusMessage.createMethodCall("org.kde.KWin", "/KaomiCaret", "kaomi.Caret", "SetPassive")
            msg.setArguments([bool(on)])
            self.bus.send(msg)
        except Exception:
            pass

    def _tell_pid(self):
        """Tell the plugin which process the panel belongs to (it lets only one
        running process have that role)."""
        try:
            from PyQt6.QtDBus import QDBusMessage
            msg = QDBusMessage.createMethodCall("org.kde.KWin", "/KaomiCaret", "kaomi.Caret", "SetPanelPid")
            msg.setArguments([os.getpid()])

            def ok(accepted):
                if not accepted and self.api >= 8 and not getattr(self, "_warned_owner", False):
                    self._warned_owner = True
                    log("text-cursor plugin: another program has registered as Kaomi with it; "
                        "typing, Escape and click detection won't work until that program quits")

            def err(message):
                pass
            r = DBusBoolReply(self, ok, err)
            if not self.bus.callWithCallback(msg, r.ok, r.err, 2000):
                r.deleteLater()
        except Exception:
            pass

    def _iface(self, path, iface):
        from PyQt6.QtDBus import QDBusInterface
        i = QDBusInterface("org.kde.KWin", path, iface, self.bus)
        i.setTimeout(400)
        return i

    def check(self):
        try:
            from PyQt6.QtDBus import QDBusMessage
            r = self._iface("/KaomiCaret", "kaomi.Caret").call("BuiltFor")
            ok = r.type() == QDBusMessage.MessageType.ReplyMessage
        except Exception:
            ok = False
        api = 0
        if ok:
            try:
                r = self._iface("/KaomiCaret", "kaomi.Caret").call("Api")
                a = r.arguments()
                api = int(a[0]) if r.type() == QDBusMessage.MessageType.ReplyMessage and a else 1
            except Exception:
                api = 1
            self._tell_pid()
        self.clicks = api >= 2
        can_commit = api >= 7              # api 7 has no way to say; it worked when it shipped
        if api >= 8:
            try:
                r = self._iface("/KaomiCaret", "kaomi.Caret").call("TextInputOk")
                a = r.arguments()
                can_commit = r.type() == QDBusMessage.MessageType.ReplyMessage and bool(a) and a[0] is True
            except Exception:
                can_commit = False
        if api >= 7 and not can_commit and not getattr(self, "_warned_commit", False):
            self._warned_commit = True
            log("text-cursor plugin: this KWin changed how text input works; emoji are pasted "
                "instead of typed until Kaomi is updated")
        self.can_commit = can_commit
        self.api = api
        if ok != self.active:
            self.active = ok
            self.activeChanged.emit(ok)
        return ok

    def cursor(self):
        """(x, y, w, h) of the text cursor on screen, or None."""
        if not self.active:
            return None
        try:
            r = self._iface("/KaomiCaret", "kaomi.Caret").call("CursorRect")
            a = r.arguments()
            if a and a[0] is not None and len(a[0]) == 4:
                return tuple(int(v) for v in a[0])
        except Exception:
            pass
        return None

    def _load(self):
        try:
            self._iface("/Plugins", "org.kde.KWin.Plugins").call("LoadPlugin", KPLUG_ID)
        except Exception:
            pass
        ok = self.check()
        log(f"text-cursor plugin: {'active' if ok else 'not loaded'}")
        return ok

    def ensure(self):
        """Never builds anything. If the plugin is outdated, show a notification."""
        if not os.environ.get("WAYLAND_DISPLAY"):
            return
        if self.check():
            if self.clicks:
                log("text-cursor plugin: active")
            else:
                log("text-cursor plugin: an older build is running; the new one (click "
                    "detection, no flicker) takes over after you log out and back in")
            self.close_notification()
            return
        sysfile = kplug_system_file()
        if not sysfile or not os.path.exists(sysfile):
            log("text-cursor plugin: not installed")
            return
        want = kplug_wanted_stamp()
        try:
            have = open(KPLUG_STAMP).read().strip()
        except OSError:
            have = None
        # KWin only checks x.y.z; the stamp also knows Ubuntu's exact package revision
        if (have is None or have == want) and self._load():
            self.close_notification()
            return
        if running_kwin_is_old():
            # KWin was updated but you haven't logged out yet: nothing to fix now
            log("text-cursor plugin: KWin updated on disk; active again after next login")
            return
        log(f"text-cursor plugin: outdated (built for {have}, KWin is now {want}); notifying")
        self.notify_outdated()

    # -- notification with an "Update now" button
    def notify_outdated(self):
        from PyQt6.QtDBus import QDBusConnection
        cmd = os.path.join(os.path.expanduser("~"), ".local", "bin", APP_ID) + " --update-kwin-plugin"
        body = ("Plasma was updated, so the emoji panel can't find the text cursor right now "
                "and opens at the mouse instead.\n\n"
                "Click <b>Update now</b> and type your password when asked. "
                "Or run this in a terminal:\n" + cmd)
        from PyQt6.QtDBus import QDBusMessage
        from PyQt6.QtCore import QVariant, QMetaType

        def typed(value, t):
            v = QVariant(value)
            v.convert(QMetaType(t.value))
            return v
        msg = QDBusMessage.createMethodCall("org.freedesktop.Notifications", "/org/freedesktop/Notifications",
                                            "org.freedesktop.Notifications", "Notify")
        msg.setArguments([
            "Kaomi",
            typed(self._notif_id or 0, QMetaType.Type.UInt),          # replaces_id: u
            APP_ID,
            "Kaomi needs a quick update",
            body,
            typed(["update", "Update now"], QMetaType.Type.QStringList),  # actions: as
            {"urgency": typed(1, QMetaType.Type.UChar)},             # hints: a{sv}
            typed(0, QMetaType.Type.Int),                            # stays until dismissed
        ])
        r = self.bus.call(msg, timeout=1500)
        from PyQt6.QtDBus import QDBusMessage
        a = r.arguments()
        if r.type() == QDBusMessage.MessageType.ReplyMessage and a:
            try:
                self._notif_id = int(a[0])
            except (TypeError, ValueError):
                pass
        else:
            log("couldn't show the notification: " + (r.errorMessage() or "no reply"))
        if not self._listening:
            QDBusConnection.sessionBus().connect(
                "org.freedesktop.Notifications", "/org/freedesktop/Notifications",
                "org.freedesktop.Notifications", "ActionInvoked", self._action)
            self._listening = True

    def close_notification(self):
        if self._notif_id:
            from PyQt6.QtDBus import QDBusMessage
            from PyQt6.QtCore import QVariant, QMetaType
            v = QVariant(self._notif_id); v.convert(QMetaType(QMetaType.Type.UInt.value))
            msg = QDBusMessage.createMethodCall("org.freedesktop.Notifications", "/org/freedesktop/Notifications",
                                                "org.freedesktop.Notifications", "CloseNotification")
            msg.setArguments([v])
            self.bus.call(msg, timeout=1500)
            self._notif_id = None

    def _iface_n(self):
        from PyQt6.QtDBus import QDBusInterface
        return QDBusInterface("org.freedesktop.Notifications", "/org/freedesktop/Notifications",
                              "org.freedesktop.Notifications", self.bus)

    @pyqtSlot("uint", str)
    def _action(self, nid, key):
        if nid != self._notif_id or key != "update":
            return
        path = os.path.join(os.path.expanduser("~"), ".local", "bin", APP_ID)
        script = '"$1" --update-kwin-plugin; echo; read -r -p "Press Enter to close this window" _'
        cmd = ["bash", "-c", script, "bash", path]
        for term in (["konsole", "-e"] + cmd, ["kitty"] + cmd, ["x-terminal-emulator", "-e"] + cmd):
            if shutil.which(term[0]):
                QProcess.startDetached(term[0], term[1:])
                break


# ------------------------------------------------------------- KWin helper --
# A tiny KWin script that lets the picker stay open while the emoji is pasted:
# the picker changes its own window title to "[back:N]" or "[front:N]", and the
# script moves keyboard focus to the previous app or back to the picker.
KWIN_SCRIPT = r"""
const APP = "%s";
const PID = __PID__;      // the picker's process id: apps can fake a name, not this
const BUS = "__BUS__";    // the picker's D-Bus address (to tell it you switched apps)
let last = null;
// passive: after you click an emoji, your app keeps keyboard focus. Clicks on the
// panel still activate it for an instant, but it's handed straight back to your
// app inside this same step, so the app never looks unfocused.
let passive = false;
// handoff: the picker itself asked for focus to go to your app (stay-open paste),
// so that activation is not you clicking away from the panel.
let handoff = false;
let pickerHadFocus = false;   // the panel was the active window since it opened
const act = workspace.windowActivated || workspace.clientActivated;
const add = workspace.windowAdded || workspace.clientAdded;
function list() { return workspace.windowList ? workspace.windowList() : workspace.clientList(); }
function setActive(w) { if (workspace.activeWindow !== undefined) workspace.activeWindow = w; else workspace.activeClient = w; }
function isPicker(w) { return w && w.pid == PID && (w.resourceClass == APP || w.resourceName == APP); }
function lastOk() { return last && list().indexOf(last) >= 0 && !last.minimized; }
function handle(w) {
    const m = /\[(back|front|passive):\d+\]/.exec(w.caption || "");
    if (!m) return;
    if (m[1] == "front") { passive = false; handoff = false; setActive(w); return; }
    if (m[1] == "passive") passive = lastOk();
    if (lastOk()) {
        // only expect an activation event if focus actually has to move
        const cur = workspace.activeWindow || workspace.activeClient;
        handoff = cur !== last;
        setActive(last);
    }
}
function pickerOpen() { return list().some(isPicker); }
function tellPicker(method) {
    try { callDBus(BUS, "/KaomiPanel", "kaomi.Panel", method); } catch (e) {}
}
let lastPos = null;
let lastSpot = null;     // last text-cursor position KWin gave us, and whose window it was in
function inside(pt, win) {
    const g = win.frameGeometry;
    return pt.x >= g.x && pt.x <= g.x + g.width && pt.y >= g.y && pt.y <= g.y + g.height;
}
function clamp(r, area) {
    r.x = Math.max(area.x, Math.min(r.x, area.x + area.width - r.width));
    r.y = Math.max(area.y, Math.min(r.y, area.y + area.height - r.height));
    return r;
}
function place(w) {
    const m = /\{place:(\w+)\}/.exec(w.caption || "");
    let mode = m ? m[1] : "caret";
    const g = w.frameGeometry;
    const r = { x: g.x, y: g.y, width: g.width, height: g.height };
    const target = (last && list().indexOf(last) >= 0 && !last.minimized) ? last : null;
    const area = workspace.clientArea(KWin.PlacementArea, target || w);
    if (mode == "caret") {
        const sp = /\{spot:(-?\d+),(-?\d+),(\d+)\}/.exec(w.caption || "");
        let cx, cy, ch;
        if (sp) {
            cx = parseInt(sp[1]); cy = parseInt(sp[2]); ch = parseInt(sp[3]);
            if (target) lastSpot = { x: cx, y: cy, h: ch, win: target };
        } else if (lastSpot && target && lastSpot.win === target && inside(lastSpot, target)) {
            // KWin forgets the text cursor while the app is unfocused (e.g. after the
            // panel closed with Escape) and the app only re-announces it once it moves.
            // Same window as last time, and the window hasn't moved away from the
            // spot: use the spot we saw then.
            cx = lastSpot.x; cy = lastSpot.y; ch = lastSpot.h;
        }
        if (cx !== undefined) {
            // exact on-screen text cursor from KWin: above it, or below if no room
            let sa = area;
            try {
                if (workspace.screenAt && workspace.currentDesktop) {
                    const scr = workspace.screenAt({ x: cx, y: cy });
                    if (scr) sa = workspace.clientArea(KWin.PlacementArea, scr, workspace.currentDesktop);
                }
            } catch (e) {}
            r.x = cx - 24;
            r.y = (cy - r.height - 6 >= sa.y) ? cy - r.height - 6 : cy + ch + 6;
            return apply(w, clamp(r, sa));
        }
        // text cursor, reported relative to the app window: go above it, or below if no room
        const cm = /\{caret:([-\d,;]+)\}/.exec(w.caption || "");
        let hit = null;
        if (cm && target) {
            cm[1].split(";").forEach(function (e) {
                const v = e.split(",").map(function (n) { return parseInt(n); });
                if (v.length == 4 && v[0] == target.pid) hit = v;
            });
        }
        if (hit) {
            const b = target.bufferGeometry || target.clientGeometry || target.frameGeometry;
            const cx = b.x + hit[1], cy = b.y + hit[2], ch = hit[3];
            const inside = cx >= b.x && cx <= b.x + b.width && cy >= b.y && cy <= b.y + b.height;
            if (inside) {
                r.x = cx - 24;
                r.y = (cy - r.height - 6 >= area.y) ? cy - r.height - 6 : cy + ch + 6;
                return apply(w, clamp(r, area));
            }
        }
        mode = "mouse";      // no text cursor info for this app: use the pointer
    }
    if (mode == "mouse") {
        // at the pointer: above it if there's room, otherwise below it
        const c = workspace.cursorPos;
        let ma = area;
        try {
            // the screen the pointer is on (Plasma 6: (option, screen, desktop))
            const scr = workspace.screenAt ? workspace.screenAt({ x: c.x, y: c.y }) : null;
            ma = scr && workspace.currentDesktop
                ? workspace.clientArea(KWin.PlacementArea, scr, workspace.currentDesktop)
                : workspace.activeScreen && workspace.currentDesktop
                    ? workspace.clientArea(KWin.PlacementArea, workspace.activeScreen, workspace.currentDesktop)
                    : workspace.clientArea(KWin.PlacementArea, w);
        } catch (e) {
            try { ma = workspace.clientArea(KWin.PlacementArea, w); } catch (e2) {}
        }
        r.x = c.x - 28;
        r.y = (c.y - r.height - 10 >= ma.y) ? c.y - r.height - 10 : c.y + 18;
        return apply(w, clamp(r, ma));
    } else if (mode == "remember" && lastPos) {
        r.x = lastPos.x; r.y = lastPos.y;
    } else if (mode == "window" && target) {
        const t = target.frameGeometry;
        r.x = t.x + (t.width - r.width) / 2; r.y = t.y + (t.height - r.height) / 2;
    } else {
        r.x = area.x + (area.width - r.width) / 2; r.y = area.y + (area.height - r.height) / 2;
    }
    apply(w, clamp(r, area));
}
function apply(w, f) {
    const r = { x: Math.round(f.x), y: Math.round(f.y), width: f.width, height: f.height };
    try {
        w.frameGeometry = r;
    } catch (e) {
        if (typeof Qt !== "undefined" && Qt.rect) w.frameGeometry = Qt.rect(r.x, r.y, r.width, r.height);
        else throw e;
    }
}
function hook(w) {
    if (!isPicker(w)) return;
    handoff = false; passive = false;
    // stay on top and out of the taskbar/switcher (set here, not by a window
    // rule, so no other app can borrow these just by using the same name)
    try { w.keepAbove = true; w.skipTaskbar = true; w.skipPager = true; w.skipSwitcher = true; } catch (e) {}
    // focus hand-off first: it must work even if positioning fails
    w.captionChanged.connect(function () {
        try { handle(w); } catch (e) { print("kaomi focus: " + e); }
    });
    w.frameGeometryChanged.connect(function () {
        try { const g = w.frameGeometry; lastPos = { x: g.x, y: g.y }; } catch (e) {}
    });
    try { place(w); } catch (e) { print("kaomi placement: " + e); }
    // the panel always wants focus when it appears. Its title may already say
    // [front:N] (set before KWin saw the window), so captionChanged won't fire.
    try { setActive(w); } catch (e) {}
}
act.connect(function (w) {
    if (handoff && w === last) {
        handoff = false;                     // focus went to your app because the picker asked
    } else if (passive && w) {
        if (isPicker(w)) {
            // a click on the panel: give focus straight back to your app
            if (lastOk()) { setActive(last); return; }
            passive = false;
        } else if (w !== last) {
            passive = false;                 // you switched to another app: close the panel
            tellPicker("OtherAppActivated");
        }
    } else if (w && !isPicker(w) && pickerHadFocus && pickerOpen()) {
        // you clicked into another app (or the desktop) while the panel is open:
        // close it, like Windows. KWin sees this even when Qt doesn't report it.
        // (only after the panel really had focus: while it is opening, focus can
        // pass through other windows for an instant)
        tellPicker("OtherAppActivated");
    }
    if (isPicker(w)) pickerHadFocus = true;
    else if (!pickerOpen()) pickerHadFocus = false;
    if (w && !isPicker(w) && !w.desktopWindow && !w.dock) last = w;
});
add.connect(hook);
list().forEach(function (w) { if (isPicker(w)) { w.captionChanged.connect(function () { handle(w); }); } });
const cur = workspace.activeWindow || workspace.activeClient;
if (cur && !isPicker(cur)) last = cur;
""" % APP_ID


def load_kwin_helper():
    """Returns True if the KWin helper script is running."""
    try:
        from PyQt6.QtDBus import QDBusInterface, QDBusConnection
        bus = QDBusConnection.sessionBus()
        if not bus.isConnected():
            return False
        os.makedirs(DATA_DIR, exist_ok=True)
        path = os.path.join(DATA_DIR, "kwin-helper.js")
        with open(path, "w") as f:
            f.write(KWIN_SCRIPT.replace("__PID__", str(os.getpid()))
                    .replace("__BUS__", bus.baseService().replace('"', "")))
        name = APP_ID + "-helper"
        sc = QDBusInterface("org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting", bus)
        if not sc.isValid():
            return False
        sc.call("unloadScript", name)
        r = sc.call("loadScript", path, name)
        args = r.arguments()
        if not args or int(args[0]) < 0:
            return False
        sid = int(args[0])
        for obj in (f"/Scripting/Script{sid}", f"/{sid}"):
            s = QDBusInterface("org.kde.KWin", obj, "org.kde.kwin.Script", bus)
            if s.isValid():
                s.call("run")
                return True
        sc.call("start")
        return True
    except Exception:
        return False



# ------------------------------------------------ messages from KWin helper --
from PyQt6.QtCore import pyqtClassInfo
from PyQt6.QtDBus import QDBusMessage as _QDBusMessage, QDBusError as _QDBusError


class DBusBoolReply(QObject):
    """Answer to an asynchronous D-Bus call returning a bool."""

    def __init__(self, parent, ok, err):
        super().__init__(parent)
        self._ok, self._err = ok, err

    @pyqtSlot(_QDBusMessage)
    def ok(self, msg):
        self.deleteLater()
        a = msg.arguments()
        self._ok(bool(a[0]) if a else False)

    @pyqtSlot(_QDBusError)
    def err(self, e):
        self.deleteLater(); self._err(e.name() + ": " + e.message())


class DBusReply(QObject):
    """Answer to one asynchronous D-Bus call: runs `ok()` or `err(message)` once."""

    def __init__(self, parent, ok, err):
        super().__init__(parent)
        self._ok, self._err = ok, err

    @pyqtSlot(_QDBusMessage)
    def ok(self, _msg):
        self.deleteLater(); self._ok()

    @pyqtSlot(_QDBusError)
    def err(self, e):
        self.deleteLater(); self._err(e.message())


@pyqtClassInfo("D-Bus Interface", "kaomi.Panel")
class PanelBus(QObject):
    """KWin's helper calls this when you switch to another app while the panel is
    open in 'your app keeps focus' mode (so it closes, like Windows)."""

    def __init__(self, picker):
        super().__init__(picker)
        self.picker = picker

    @pyqtSlot()
    def OtherAppActivated(self):
        QTimer.singleShot(0, self.picker.on_other_app)


def register_panel_bus(picker):
    try:
        from PyQt6.QtDBus import QDBusConnection
        bus = QDBusConnection.sessionBus()
        if not bus.isConnected():
            return None
        obj = PanelBus(picker)
        if not bus.registerObject("/KaomiPanel", obj,
                                  QDBusConnection.RegisterOption.ExportAllSlots):
            return None
        return obj
    except Exception:
        return None


# -------------------------------------------------------- clipboard lending --
class EmojiMime(QMimeData):
    """Clipboard data that tells us when another app actually reads it."""

    def __init__(self, on_read):
        super().__init__()
        self._on_read = on_read

    def retrieveData(self, mimetype, preferred):
        if mimetype != SECRET_HINT:
            QTimer.singleShot(0, self._on_read)
        return super().retrieveData(mimetype, preferred)


SECRET_HINT = "x-kde-passwordManagerHint"


OWN_MARK = "x-kaomi-own"      # tags clipboard writes made by the picker itself


def snap_hash(snap):
    return hashlib.sha1(snap.data).hexdigest()


def snap_of_item(it, plain=False):
    if it.kind == "text":
        return Snap("text/plain;charset=utf-8", it.payload.encode(), None if plain else it.html)
    return Snap(it.mime, it.payload)


class Snap:
    """What was on the clipboard, kept so it can be put back after an insert.
    extra: more (mime, data) pairs offered together when we can (Qt path)."""

    def __init__(self, mime, data, html=None, extra=None):
        self.mime, self.data, self.html, self.extra = mime, data, html, extra or []


class ClipboardLender:
    """Puts the emoji on the clipboard just long enough to paste it, keeps it out
    of clipboard history, and then restores whatever you had copied before.

    Rules that keep this safe:
      * It never reads the clipboard at pick time; the watcher already holds a
        snapshot of your latest copy.
      * It only restores while it still owns the clipboard. If anything else
        copied in the meantime (you, a password manager, ...), it leaves it alone.
      * Anything marked secret (passwords) is never snapshotted or restored."""

    def __init__(self, picker):
        self.picker = picker
        self.pending = None      # ("snap", Snap) | ("deferred", None) | ("none", None)
        self.pasted_at = None
        self.gen = 0
        self.tries = 0
        self.read_gen = -1       # last lend the target app actually read

    def _use_primary(self):
        cb = QGuiApplication.clipboard()
        return cb.supportsSelection() and self.picker.conf.get("paste_keys") == "shift+insert"

    def _what_to_restore(self):
        w = self.picker.watcher
        if w.active():
            if w.in_flight():
                return ("deferred", None)     # a copy is being read right now
            return ("snap", w.current) if w.current is not None else ("none", None)
        # history off: remember plain text only, and never a password
        md = QGuiApplication.clipboard().mimeData(QClipboard.Mode.Clipboard)
        if md is not None and md.hasText() and not md.hasFormat("x-kaomi") \
                and not md.hasFormat(SECRET_HINT):
            return ("snap", Snap("text/plain;charset=utf-8", md.text().encode()))
        return ("none", None)

    def lend(self, text):
        cb = QGuiApplication.clipboard()
        self.gen += 1
        gen = self.gen
        self.pasted_at = None
        self.tries = 0
        self.picker.watcher.lent_at = time.monotonic()
        if self.pending is None:   # keep the original if a restore is still pending
            self.pending = self._what_to_restore()
        modes = [QClipboard.Mode.Clipboard]
        if self._use_primary():
            modes.append(QClipboard.Mode.Selection)   # Shift+Insert in terminals reads this
            self.lent_primary = True
        for mode in modes:
            m = EmojiMime(lambda gen=gen: self._read(gen))
            m.setText(text)
            # clipboard history tools ignore data with this hint
            m.setData(SECRET_HINT, QByteArray(b"secret"))
            m.setData("x-kaomi", QByteArray(b"1"))
            cb.setMimeData(m, mode)
        # safety net: restore even if we never notice the paste
        QTimer.singleShot(2500, lambda: self.restore(gen))

    def cancel(self):
        """Forget a pending restore (the user chose a clipboard item on purpose)."""
        self.gen += 1
        self.pending = None

    def about_to_paste(self):
        self.pasted_at = time.monotonic()

    def _read(self, gen):
        # only reads after our keypress count
        if self.pasted_at is not None and gen == self.gen:
            self.read_gen = gen
            QTimer.singleShot(150, lambda: self.restore(gen))

    @staticmethod
    def _still_ours(mode):
        """True if the clipboard still holds our emoji (nobody copied since)."""
        cb = QGuiApplication.clipboard()
        if QGuiApplication.platformName() == "offscreen":     # headless tests: no ownership info
            md = cb.mimeData(mode)
            return md is not None and md.hasFormat("x-kaomi")
        return cb.ownsClipboard() if mode == QClipboard.Mode.Clipboard else cb.ownsSelection()

    def _can_set_directly(self):
        # Qt may set the clipboard when we have focus, and always on X11.
        # In passive mode every click on the panel is fresh input, which KWin also accepts.
        return self.picker.isActiveWindow() or self.picker.passive or not os.environ.get("WAYLAND_DISPLAY")

    def restore(self, gen):
        if gen != self.gen or self.pending is None:
            return
        kind, snap = self.pending
        if kind == "deferred":
            w = self.picker.watcher
            if w.in_flight() and self.tries < 30:      # wait for that copy to finish reading
                self.tries += 1
                QTimer.singleShot(100, lambda: self.restore(gen))
                return
            kind, snap = ("snap", w.current) if w.current is not None else ("none", None)
        self.pending = None
        cb = QGuiApplication.clipboard()

        # middle-click selection: don't leave the emoji there (reading the old
        # selection at pick time could stall, so it is cleared instead)
        lent_primary, self.lent_primary = getattr(self, "lent_primary", False), False
        if lent_primary and cb.supportsSelection() and self._still_ours(QClipboard.Mode.Selection):
            if self._can_set_directly():
                cb.clear(QClipboard.Mode.Selection)
            else:
                tool, args, _ = copy_command(None, primary=True)
                if tool and os.environ.get("WAYLAND_DISPLAY"):
                    QProcess.startDetached(tool, args)

        # clipboard: only if nothing else has been copied since we lent it
        if not self._still_ours(QClipboard.Mode.Clipboard):
            return
        if kind == "none" or snap is None:
            return
        self.picker.write_clipboard(snap)


# ------------------------------------------------------ clipboard history ---
class ClipItem:
    def __init__(self, kind, payload, mime, pinned=False, iid=None, html=None):
        self.id = iid or uuid.uuid4().hex
        self.html = html          # formatted version (from browsers, documents), if any
        self.kind = kind          # "text" | "image"
        self.payload = payload    # str for text, bytes for image
        self.mime = mime
        self.pinned = pinned
        raw = payload.encode() if kind == "text" else payload
        self.hash = hashlib.sha1(raw).hexdigest()
        self._thumb = None
        self._preview = None

    def preview(self, max_h):
        """Small copy for the history card, made once: scaling a full screenshot
        on every open is what makes a long history slow to show."""
        if self._preview is None or self._preview[0] != max_h:
            pm = self.thumb_full()
            if not pm.isNull() and pm.height() > max_h * 2:
                pm = pm.scaledToHeight(max_h * 2, Qt.TransformationMode.SmoothTransformation)
            self._preview = (max_h, pm)
        return self._preview[1]

    def thumb_full(self):
        if self._thumb is None:
            pm = QPixmap()
            pm.loadFromData(self.payload)
            self._thumb = pm
        return self._thumb

    def thumb(self, w, h):
        if self._thumb is None:
            pm = QPixmap()
            pm.loadFromData(self.payload)
            self._thumb = pm
        pm = self._thumb
        if pm.isNull():
            return pm
        return pm.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)


class ClipStore(QObject):
    """History lives only in memory; pinned items are saved to disk."""
    changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.history = []   # newest first, unpinned
        self.pinned = []    # saved to disk, shown first
        self.load_pinned()

    def items(self):
        return self.pinned + self.history

    # -- capture
    def add(self, kind, payload, mime, html=None):
        it = ClipItem(kind, payload, mime, html=html)
        for p in self.pinned:
            if p.hash == it.hash:
                return p
        old = next((h for h in self.history if h.hash == it.hash), None)
        if old is not None and not it.html and old.html:
            it.html = old.html            # same text again without formatting: keep it
        self.history = [h for h in self.history if h.hash != it.hash]
        self.history.insert(0, it)
        self._trim()
        self.changed.emit()
        return it

    def _trim(self):
        """Keep the list to CLIP_MAX items and images to CLIP_IMAGE_BUDGET bytes
        (a day of screenshots must not eat the RAM); oldest go first."""
        del self.history[CLIP_MAX:]
        total = 0
        keep = []
        for h in self.history:                  # newest first
            if h.kind == "image":
                total += len(h.payload)
                if total > CLIP_IMAGE_BUDGET:
                    continue
            keep.append(h)
        self.history = keep

    # -- actions
    def delete(self, it):
        if it.pinned:
            self.pinned = [p for p in self.pinned if p.id != it.id]
            self.save_pinned()
        else:
            self.history = [h for h in self.history if h.id != it.id]
        self.changed.emit()

    def pin(self, it):
        if it.pinned:
            return
        self.history = [h for h in self.history if h.id != it.id]
        it.pinned = True
        self.pinned.insert(0, it)
        self.save_pinned()
        self.changed.emit()

    def unpin(self, it):
        """Unpinning forgets it from disk and treats it like a fresh copy."""
        if not it.pinned:
            return
        self.pinned = [p for p in self.pinned if p.id != it.id]
        self.save_pinned()
        it.pinned = False
        self.history = [h for h in self.history if h.hash != it.hash]
        self.history.insert(0, it)
        self._trim()
        self.changed.emit()

    def clear(self):
        self.history = []
        self.changed.emit()

    # -- storage (pinned only)
    def load_pinned(self):
        try:
            with open(os.path.join(PIN_DIR, "pinned.json")) as f:
                meta = json.load(f)
        except Exception:
            return
        if not isinstance(meta, list):
            return
        for m in meta:
            if not isinstance(m, dict):
                continue
            try:
                if not re.fullmatch(r"[0-9a-f]{32}", str(m["id"])):
                    continue                     # ids are only ever uuid hex; anything else is tampering
                if m["kind"] == "text":
                    payload = m["text"]
                else:
                    with open(os.path.join(PIN_DIR, m["id"] + ".img"), "rb") as f:
                        payload = f.read()
                self.pinned.append(ClipItem(m["kind"], payload, m["mime"], True, m["id"], m.get("html")))
            except Exception:
                pass

    def save_pinned(self):
        try:
            os.makedirs(PIN_DIR, mode=0o700, exist_ok=True)
            os.chmod(PIN_DIR, 0o700)             # also for a folder made by an older version
            meta, keep = [], {"pinned.json"}
            for it in self.pinned:
                m = {"id": it.id, "kind": it.kind, "mime": it.mime}
                if it.kind == "text":
                    m["text"] = it.payload
                    if it.html:
                        m["html"] = it.html
                else:
                    m["file"] = it.id + ".img"
                    keep.add(m["file"])
                    path = os.path.join(PIN_DIR, m["file"])
                    if not os.path.exists(path):
                        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT, 0o600), "wb") as f:
                            f.write(it.payload)
                meta.append(m)
            tmp = os.path.join(PIN_DIR, "pinned.json.tmp")
            with open(tmp, "w") as f:
                json.dump(meta, f, ensure_ascii=False)
            os.replace(tmp, os.path.join(PIN_DIR, "pinned.json"))
            for name in os.listdir(PIN_DIR):   # unpinned/deleted images are removed from disk
                if name not in keep:
                    try:
                        os.remove(os.path.join(PIN_DIR, name))
                    except OSError:
                        pass
        except Exception:
            pass


# The installer builds a newer wl-clipboard here: Plasma 6 only offers the newer
# "ext-data-control" clipboard protocol, which older wl-clipboard can't use.
WLC_BIN = os.path.join(os.path.expanduser("~"), ".local", "opt", APP_ID, "wl-clipboard", "bin")


def wlc(tool):
    local = os.path.join(WLC_BIN, tool)
    return local if os.access(local, os.X_OK) else shutil.which(tool)


# kaomi-copy (built by the installer from KAOMI_COPY_C) sets the clipboard with
# several formats at once, so a restore keeps HTML formatting and file lists.
KAOMI_COPY = os.path.join(os.path.expanduser("~"), ".local", "opt", APP_ID, "kaomi-copy", "bin", "kaomi-copy")


def kaomi_copy():
    return KAOMI_COPY if os.access(KAOMI_COPY, os.X_OK) else None


def snap_records(snap):
    """Everything a Snap holds, as (mime, bytes) pairs for kaomi-copy. Plain text
    is offered under the usual alias names too, like wl-copy does."""
    if snap is None:
        return []
    out = []
    seen = set()

    def add(mime, data):
        if mime not in seen:
            seen.add(mime); out.append((mime, data))
    if snap.mime.startswith("text/plain"):
        for t in TEXT_TYPES:
            add(t, snap.data)
        if snap.html:
            add("text/html", snap.html.encode("utf-8", errors="replace"))
    else:
        add(snap.mime, snap.data)
    for mime, data in snap.extra:
        if mime.startswith("text/plain"):
            for t in TEXT_TYPES:
                add(t, data)
        else:
            add(mime, data)
    return out


def copy_command(snap, primary=False):
    """(program, args, stdin bytes) that puts `snap` on the clipboard (None: empties
    it) from an unfocused program: kaomi-copy with every format, else wl-copy."""
    kc = kaomi_copy()
    if kc:
        recs = snap_records(snap)
        payload = b"".join(f"{m} {len(d)}\n".encode() + d for m, d in recs)
        return kc, (["--primary"] if primary else []), payload
    tool = wlc("wl-copy")
    if not tool:
        return None, [], b""
    pri = ["--primary"] if primary else []
    if snap is None:
        return tool, pri + ["--clear"], b""
    # plain text: no --type, so wl-copy offers every usual text format
    return tool, pri + ([] if snap.mime.startswith("text/plain") else ["--type", snap.mime]), snap.data


TEXT_TYPES = ["text/plain;charset=utf-8", "UTF8_STRING", "text/plain", "TEXT", "STRING"]
SKIP_TYPES = {SECRET_HINT, "x-kaomi"}
KLIPPER_REFILL = "application/x-kde-onlyReplaceEmpty"   # Klipper re-setting an old item


class ClipWatcher(QObject):
    """Notices every copy. On Wayland apps can't see the clipboard while
    unfocused, so this uses wl-paste (wl-clipboard), which Plasma allows to
    watch it. On X11 Qt's own signal is enough."""

    def __init__(self, store):
        super().__init__()
        self.store = store
        self.proc = None
        self.busy = False
        self.pending = False
        self.wl_paste = wlc("wl-paste")
        self.wayland = bool(os.environ.get("WAYLAND_DISPLAY")) and self.wl_paste
        self.error = None
        if os.environ.get("WAYLAND_DISPLAY") and not self.wl_paste:
            self.error = "wl-clipboard is not installed"
        self.current = None      # Snap of what is on the clipboard right now (None: nothing restorable)
        self.lent_at = 0.0       # when the picker last put an emoji on the clipboard
        self.expect = None       # (hash, deadline) of a write the picker just made itself
        self.epoch = 0           # bumped by delete / Clear all: older reads are discarded
        self.x11 = False
        self.restarts = 0
        self.started_at = 0.0
        self.timer = QTimer(self); self.timer.setSingleShot(True); self.timer.setInterval(30)
        self.timer.timeout.connect(self.fetch)
        self.restart_timer = QTimer(self); self.restart_timer.setSingleShot(True)
        self.restart_timer.setInterval(3000); self.restart_timer.timeout.connect(self.start)

    def start(self):
        if self.wayland:
            if self.proc:
                return
            self.proc = QProcess(self)
            self.proc.setProgram(self.wl_paste)
            self.proc.setArguments(["--watch", "echo", "."])
            self.proc.readyReadStandardOutput.connect(self._changed)
            self.proc.readyReadStandardError.connect(self._stderr)
            self.proc.finished.connect(self._died)
            self.proc.errorOccurred.connect(lambda e: e == QProcess.ProcessError.FailedToStart and self._died())
            self.proc.start()
            self.started_at = time.monotonic()
            log(f"clipboard watcher started ({self.wl_paste} --watch)")
        elif not os.environ.get("WAYLAND_DISPLAY"):
            if not self.x11:
                QGuiApplication.clipboard().dataChanged.connect(self._qt_changed)
                self.x11 = True

    def _stderr(self):
        msg = bytes(self.proc.readAllStandardError()).decode(errors="ignore").strip()
        if msg:
            log("wl-paste: " + msg)
            self.error = "wl-paste says: " + msg.splitlines()[-1]

    def _died(self, *_):
        if self.proc is None:
            return
        log("clipboard watcher stopped, restarting in 3s")
        self.proc.deleteLater(); self.proc = None
        if time.monotonic() - self.started_at > 60:
            self.restarts = 0            # it ran fine for a while: not a crash loop
        self.restarts += 1
        if self.restarts <= 5:
            self.restart_timer.start()
        self.store.changed.emit()

    def stop(self):
        self.restart_timer.stop()
        if self.proc:
            p = self.proc; self.proc = None
            p.finished.disconnect(); p.kill()
            p.waitForFinished(500)
        if self.x11:
            try:
                QGuiApplication.clipboard().dataChanged.disconnect(self._qt_changed)
            except TypeError:
                pass
            self.x11 = False
        self.current = None

    def active(self):
        return self.proc is not None or self.x11

    def note_own_write(self, snap):
        """The picker just put `snap` on the clipboard (None = emptied it): that is
        what the clipboard holds now, and it must not show up as a new copy."""
        self.current = snap
        # an emptied clipboard has no echo to wait for: whatever comes next is a real copy
        self.expect = (snap_hash(snap), time.monotonic() + 3) if snap is not None else None

    def forget(self):
        """Clear all / Delete: the clipboard is (or is about to be) empty. Reads that
        began before this are thrown away, and nothing is expected back."""
        self.epoch += 1
        self.current = None
        self.expect = None

    def in_flight(self):
        """A clipboard change is noticed but not fully read yet."""
        return self.busy or self.pending or self.timer.isActive()

    def _changed(self):
        self.proc.readAllStandardOutput()
        self.timer.start()

    # -- Wayland: ask wl-paste what is on the clipboard, then read it.
    # Everything is asynchronous so the picker never freezes (it may itself be
    # the app that owns the clipboard and has to answer these reads).
    def _async(self, args, done):
        p = QProcess(self)
        state = {"fin": False}

        def finished(code=-1, _st=None):
            if state["fin"]:
                return
            state["fin"] = True
            out = bytes(p.readAllStandardOutput()) if code == 0 else None
            p.deleteLater()
            done(out)

        def error(e):
            if e == QProcess.ProcessError.FailedToStart:
                finished(-1)             # never leave the watcher stuck "busy"

        def timeout():
            if not state["fin"]:
                if p.state() == QProcess.ProcessState.NotRunning:
                    finished(-1)
                else:
                    p.kill()
        p.finished.connect(finished)
        p.errorOccurred.connect(error)
        p.start(self.wl_paste, args)
        QTimer.singleShot(3000, timeout)

    def fetch(self):
        if self.busy:
            self.pending = True
            return
        self.busy = True
        self._async(["--list-types"], self._got_types)

    def _got_types(self, types):
        if not types:
            # empty: unless the picker just wrote something itself (Klipper empties the
            # clipboard for an instant before that write lands)
            if not (self.expect is not None and time.monotonic() < self.expect[1]):
                self.current = None
            return self._done()
        tl = [t.strip() for t in types.decode(errors="ignore").splitlines() if t.strip()]
        self._store_from(tl, None)

    def _done(self):
        self.busy = False
        if self.pending:
            self.pending = False
            self.timer.start()

    # -- X11
    def _qt_changed(self):
        md = QGuiApplication.clipboard().mimeData()
        if md is None:
            return
        self._store_from(list(md.formats()), lambda t: bytes(md.data(t)))

    def _store_from(self, types, read):
        """read=None means Wayland (read asynchronously with wl-paste)."""
        wayland = read is None
        epoch = self.epoch

        def finish():
            if wayland:
                self._done()
        if "x-kaomi" in types or OWN_MARK in types:
            if OWN_MARK in types:
                self.expect = None             # the write landed; the next copy is a real one
            return finish()                    # the picker's own write: already known
        if KLIPPER_REFILL in types:
            # Plasma's clipboard putting an old item back after the clipboard was
            # emptied ("Prevent empty clipboard"): never a copy the user made
            log("clipboard: ignored Klipper putting an old item back")
            return finish()
        if SECRET_HINT in types:
            self.current = None                # a password: never kept, never restored
            return finish()
        text_t = next((t for t in TEXT_TYPES if t in types), None)
        img_t = "image/png" if "image/png" in types else next((t for t in types if t.startswith("image/")), None)
        uri_t = "text/uri-list" if "text/uri-list" in types else None
        want_html = text_t is not None and "text/html" in types

        # read what we need, then (on Wayland) re-check the types before keeping
        # anything, so a password copied mid-read is never recorded
        plan = []
        if uri_t:
            plan.append(uri_t)                 # copied files: restore them as files
        if text_t:
            plan.append(text_t)
            if want_html:
                plan.append("text/html")
        elif img_t:
            plan.append(img_t)
        if not plan:
            self.current = None
            return finish()
        got = {}
        starts = []

        def commit():
            if epoch != self.epoch:
                return finish()                # read started before a delete / Clear all
            text = got.get(text_t) if text_t else None
            html = got.get("text/html")
            img = got.get(img_t) if (img_t and not text_t) else None
            uri = got.get(uri_t) if uri_t else None
            main = text if text is not None else img if img is not None else uri
            if self.expect is not None and time.monotonic() < self.expect[1] and main is not None \
                    and hashlib.sha1(main).hexdigest() == self.expect[0]:
                self.expect = None             # echo of the picker's own write (via wl-copy)
                return finish()
            snap = None
            if text is not None and len(text) <= CLIP_RESTORE_MAX:
                t = text.decode("utf-8", errors="replace")
                h = html.decode("utf-8", errors="replace") if html and len(html) <= CLIP_TEXT_MAX else None
                snap = Snap("text/plain;charset=utf-8", text, h)
                if t.strip() and len(text) <= CLIP_TEXT_MAX:
                    self.store.add("text", t, "text/plain;charset=utf-8", h)
            elif img is not None and len(img) <= CLIP_RESTORE_MAX:
                snap = Snap(img_t, img)
                if len(img) <= CLIP_IMAGE_MAX:
                    self.store.add("image", img, img_t)
            if uri and len(uri) <= CLIP_TEXT_MAX:
                if uri.lstrip().startswith(b"file:"):
                    # copied files: restore them as files (text as a fallback format)
                    snap = Snap(uri_t, uri, extra=[(snap.mime, snap.data)] if snap else None)
                elif snap is not None:
                    snap.extra.append((uri_t, uri))        # a link: text first, link list too
                else:
                    snap = Snap(uri_t, uri)
            self.current = snap
            finish()

        def step(i):
            if i >= len(plan):
                if not wayland:
                    return commit()
                # re-check: if the clipboard changed to a secret meanwhile, drop it
                def recheck(types2):
                    tl2 = [x.strip() for x in (types2 or b"").decode(errors="ignore").splitlines() if x.strip()]
                    if "x-kaomi" in tl2:
                        # our own emoji was lent while reading: the data is the user's
                        # copy only if every read started before that
                        if starts and max(starts) < self.lent_at:
                            return commit()
                        self.current = None
                        return finish()
                    if SECRET_HINT in tl2 or not tl2:
                        self.current = None          # a password arrived mid-read: drop it
                        return finish()
                    commit()
                return self._async(["--list-types"], recheck)
            t = plan[i]
            if wayland:
                starts.append(time.monotonic())
                self._async(["--no-newline", "--type", t], lambda d: (got.__setitem__(t, d), step(i + 1)))
            else:
                got[t] = read(t)
                step(i + 1)
        step(0)


_WRAP_CACHE = {}


def _glued(word, i):
    """True if cutting word at i would split an emoji sequence / flag / keycap."""
    if i <= 0 or i >= len(word):
        return False
    a, b = word[i - 1], word[i]
    return (a == "\u200d" or b in "\u200d\ufe0f\ufe0e\u20e3" or "\U0001F3FB" <= b <= "\U0001F3FF"
            or ("\U000E0020" <= b <= "\U000E007F")
            or ("\U0001F1E6" <= a <= "\U0001F1FF" and "\U0001F1E6" <= b <= "\U0001F1FF"
                and sum(1 for c in word[:i] if "\U0001F1E6" <= c <= "\U0001F1FF") % 2 == 1))


def _safe_cut(text, n):
    """text[:n] moved back so it doesn't end inside an emoji sequence."""
    if len(text) <= n:
        return text
    while n > 1 and _glued(text, n):
        n -= 1
    return text[:n]


def wrap_lines(text, fm, width, max_lines):
    """Word-wrap text to at most max_lines lines at this pixel width, ending with … if cut.
    Only ever measures short pieces (emoji are slow to measure) and never splits
    a single character/emoji sequence in two."""
    key = (text[:600], len(text), width, max_lines, fm.height(), fm.averageCharWidth())
    hit = _WRAP_CACHE.get(key)
    if hit is not None:
        return hit
    from PyQt6.QtCore import QTextBoundaryFinder
    per_line = max(8, int(width / max(1, fm.averageCharWidth()) * 1.6))
    budget = per_line * (max_lines + 1)

    def fits(piece):
        return fm.horizontalAdvance(piece) <= width

    def cut_point(word):
        """Longest prefix (at a character boundary) that fits the width."""
        hi = min(len(word), per_line)
        while hi < len(word) and fits(word[:hi]):
            hi = min(len(word), hi * 2)
        lo, hi2 = 1, hi
        while lo < hi2:
            mid = (lo + hi2 + 1) // 2
            if fits(word[:mid]):
                lo = mid
            else:
                hi2 = mid - 1
        f = QTextBoundaryFinder(QTextBoundaryFinder.BoundaryType.Grapheme, word)
        f.setPosition(lo)
        if not f.isAtBoundary():
            p = f.toPreviousBoundary()
            if p > 0:
                lo = p
            else:
                f.setPosition(lo)
                lo = max(1, f.toNextBoundary())
        # older Qt doesn't know emoji sequences: never cut next to a joiner,
        # before a skin tone / style marker, or inside a flag pair
        def glued(i):
            return _glued(word, i)
        start = lo
        while lo > 1 and glued(lo):
            lo -= 1
        if lo <= 1 and glued(lo):          # one sequence wider than the line: keep it whole
            lo = start
            while lo < len(word) and glued(lo):
                lo += 1
        return lo

    lines = []
    capped = _safe_cut(text, budget * 2)
    truncated = len(capped) < len(text)          # anything cut off must end with …
    paras = capped.replace("\t", "    ").strip("\n").splitlines()[:max_lines + 1] or [""]
    for pi, para in enumerate(paras):
        if len(para) > budget:
            para = _safe_cut(para, budget); truncated = True
        body = para.lstrip(" ")
        cur = para[:len(para) - len(body)]          # keep the line's indentation
        if fm.horizontalAdvance(cur) > width // 2:
            cur = cur[:8]
        for word in body.split(" "):
            if len(word) > budget:
                word = _safe_cut(word, budget); truncated = True
            trial = (cur + word) if not cur.strip() else (cur + " " + word)
            if len(trial) <= per_line * 2 and fits(trial):
                cur = trial
                continue
            if cur:
                lines.append(cur); cur = ""
            # long word / URL: cut it into lines (never measures more than ~2 lines of it)
            while len(lines) <= max_lines and (len(word) > per_line * 2 or not fits(word)):
                n = cut_point(word)
                lines.append(word[:n]); word = word[n:]
                if not word:
                    break
            cur = word
            if len(lines) > max_lines:
                break
        lines.append(cur)
        if len(lines) > max_lines:
            truncated = True
            break
        if len(lines) == max_lines and pi < len(paras) - 1:
            truncated = True
            break
    out = lines[:max_lines]
    if truncated and out:
        out[-1] = fm.elidedText(out[-1] + " …", Qt.TextElideMode.ElideRight, width)
    # keep indentation visible (labels would collapse leading spaces)
    out = [ln[:len(ln) - len(ln.lstrip(" "))].replace(" ", "\u00a0") + ln.lstrip(" ") for ln in out]
    res = "\n".join(out)
    if len(_WRAP_CACHE) > 512:
        _WRAP_CACHE.clear()
    _WRAP_CACHE[key] = res
    return res


class WrapLabel(QLabel):
    """Shows up to N lines of text, wrapped to its real width and cut with …"""

    def __init__(self, text, max_lines=3):
        super().__init__()
        self.full, self.max_lines, self._w = text, max_lines, -1
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(20)
        self.rewrap(240)

    def rewrap(self, w):
        if w == self._w or w < 20:
            return
        self._w = w
        fm = QFontMetrics(self.font())
        t = wrap_lines(self.full, fm, w - 2, self.max_lines)
        self.setText(t)
        self.setFixedHeight(fm.lineSpacing() * (t.count("\n") + 1) + 2)

    def resizeEvent(self, ev):
        self.rewrap(self.width())
        super().resizeEvent(ev)


class ThumbLabel(QLabel):
    """Image preview that shrinks to fit the card instead of pushing it wider."""

    def __init__(self, pm, max_h=90):
        super().__init__()
        self.pm, self.max_h, self._w = pm, max_h, -1
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(20)
        self.rescale(240)

    def rescale(self, w):
        if w == self._w or w < 20:
            return
        self._w = w
        if self.pm.isNull():
            self.setText("[image]"); self.setFixedHeight(24); return
        sc = self.pm.scaled(min(w, self.pm.width()), min(self.max_h, self.pm.height()),
                            Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.setPixmap(sc)
        self.setFixedHeight(sc.height())

    def resizeEvent(self, ev):
        self.rescale(self.width())
        super().resizeEvent(ev)


class ClipRow(QWidget):
    """One clipboard item. Same height for every item (like Windows); the ... button
    slides it left to reveal "Paste as text" and "Delete". Delete lands exactly
    where ... was, so clicking ... twice deletes."""
    GAP = 8

    def __init__(self, page, it, h):
        super().__init__()
        self.page, self.it, self.h = page, it, h
        self.opened = False
        t = page.picker.theme
        self.setFixedHeight(h)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.slider = QWidget(self)

        self.card = QFrame(self.slider)
        self.card.setObjectName("card")
        self.card.setCursor(Qt.CursorShape.PointingHandCursor)
        self.card.installEventFilter(self)
        lay = QHBoxLayout(self.card); lay.setContentsMargins(12, 9, 4, 5); lay.setSpacing(6)
        if it.kind == "text":
            body = WrapLabel(it.payload, 3)
            body.setObjectName("cardText")
        else:
            body = ThumbLabel(it.preview(h - 16), h - 16)
        body.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay.addWidget(body, 1, Qt.AlignmentFlag.AlignTop)            # text starts at the top
        side = QVBoxLayout(); side.setSpacing(0); side.setContentsMargins(0, 0, 0, 0)
        self.more = self._small_btn("more", t.sub.name(), "See more", lambda: page.toggle_row(self))
        if it.pinned:
            self.pin = self._small_btn("pinned", t.accent.name(), "Unpin", lambda: page.store.unpin(it))
        else:
            self.pin = self._small_btn("pin", t.sub.name(), "Pin", lambda: page.store.pin(it))
        side.addWidget(self.more, 0, Qt.AlignmentFlag.AlignRight)
        side.addStretch()
        side.addWidget(self.pin, 0, Qt.AlignmentFlag.AlignRight)
        lay.addLayout(side)

        self.btn_text = self._action_btn("pastetext", "Paste as text",
                                         lambda: page.activate(it, "mouse", plain=True))
        self.btn_text.setEnabled(it.kind == "text")
        self.btn_del = self._action_btn("delete", "Delete", lambda: page.picker.delete_clip_item(it))

        self.anim = QPropertyAnimation(self.slider, b"pos", self)
        self.anim.setDuration(170)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.set_selected(False)

    def _small_btn(self, icon, color, tip, fn):
        b = QToolButton(); b.setIcon(svg_icon(icon, color, 16)); b.setIconSize(QSize(16, 16))
        b.setAutoRaise(True); b.setFixedSize(30, 26); b.setToolTip(tip)
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus); b.clicked.connect(fn)
        return b

    def _action_btn(self, icon, tip, fn):
        b = QToolButton(self.slider); b.setObjectName("action")
        b.setIcon(svg_icon(icon, self.page.picker.theme.text.name(), 20)); b.setIconSize(QSize(20, 20))
        b.setToolTip(tip); b.setFocusPolicy(Qt.FocusPolicy.NoFocus); b.clicked.connect(fn)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        return b

    def slide_dist(self):
        return 2 * (self.h + self.GAP)

    def resizeEvent(self, ev):
        w, h, g = self.width(), self.h, self.GAP
        self.anim.stop()
        self.slider.setGeometry(-self.slide_dist() if self.opened else 0, 0, w + self.slide_dist(), h)
        self.card.setGeometry(0, 0, w, h)
        self.btn_text.setGeometry(w + g, 0, h, h)
        self.btn_del.setGeometry(w + 2 * g + h, 0, h, h)
        super().resizeEvent(ev)

    def set_open(self, on, animate=True):
        if on == self.opened:
            return
        self.opened = on
        target = QPoint(-self.slide_dist() if on else 0, 0)
        self.anim.stop()
        if animate:
            self.anim.setStartValue(self.slider.pos()); self.anim.setEndValue(target); self.anim.start()
        else:
            self.slider.move(target)

    def set_selected(self, on):
        if self.card.property("sel") is on:
            return                              # re-polishing every row is slow with a long history
        self.card.setProperty("sel", on)
        self.card.style().unpolish(self.card); self.card.style().polish(self.card)

    def eventFilter(self, obj, ev):
        if obj is self.card and ev.type() == QEvent.Type.MouseButtonRelease \
                and ev.button() == Qt.MouseButton.LeftButton and self.card.rect().contains(ev.position().toPoint()):
            if self.opened:
                self.set_open(False)            # click the slid card: slide back
            else:
                self.page.close_rows()
                self.page.activate(self.it, "mouse")
            return True
        return super().eventFilter(obj, ev)


class ClipboardPage(QWidget):
    BATCH = 12          # rows built at a time; more are added as you scroll down

    def __init__(self, picker, store):
        super().__init__()
        self.picker, self.store = picker, store
        self.cards = []
        self.items = []
        self.row_h = 80
        self.sel = 0
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 4, 0, 0); lay.setSpacing(8)
        top = QHBoxLayout(); top.setContentsMargins(6, 0, 2, 0)
        title = QLabel("Clipboard"); title.setObjectName("heading")
        self.clear_btn = QPushButton("Clear all"); self.clear_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.clear_btn.clicked.connect(lambda: self.picker.clear_clip_history())
        top.addWidget(title); top.addStretch(); top.addWidget(self.clear_btn)
        lay.addLayout(top)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.inner = QWidget()
        self.inner.installEventFilter(self)          # click on empty space: slide rows back
        self.list = QVBoxLayout(self.inner); self.list.setContentsMargins(0, 0, 10, 4); self.list.setSpacing(8)
        self.scroll.setWidget(self.inner)
        self.scroll.verticalScrollBar().valueChanged.connect(self._near_end)
        self.scroll.verticalScrollBar().rangeChanged.connect(self._near_end)
        lay.addWidget(self.scroll, 1)
        self.dirty = False
        store.changed.connect(self.on_store_changed)
        self.rebuild()

    def on_store_changed(self):
        # building cards costs time; only do it while the list is on screen
        if self.isVisible():
            self.rebuild()
        else:
            self.dirty = True

    def showEvent(self, ev):
        if self.dirty:
            self.rebuild()
        super().showEvent(ev)

    def rebuild(self):
        self.dirty = False
        keep = self.cards[self.sel].it.id if 0 <= self.sel < len(self.cards) else None
        while self.list.count():
            w = self.list.takeAt(0).widget()
            if w:
                w.hide(); w.setParent(None); w.deleteLater()
        self.cards = []
        items = self.store.items()
        if not items:
            msg = self.picker.clip_status_message()
            empty = QLabel(msg); empty.setWordWrap(True)
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.list.addSpacing(40); self.list.addWidget(empty)
        fm = QFontMetrics(self.font())
        self.row_h = max(80, fm.lineSpacing() * 3 + 26)     # same height for every item
        self.items = items
        self.list.addStretch()
        self.clear_btn.setEnabled(bool(self.store.history))
        ids = [it.id for it in items]
        if keep in ids:
            self.sel = ids.index(keep)             # same item stays selected after reordering
        self.sel = min(self.sel, len(items) - 1) if items else 0
        # building every row up front made a long history slow to open: build
        # one screenful (and up to the selected item), the rest as you scroll
        self._more(max(self.BATCH, self.sel + 1))
        self.select(self.sel, scroll=False)

    def _more(self, upto):
        """Build rows until there are `upto` of them (or no more items)."""
        upto = min(upto, len(self.items))
        while len(self.cards) < upto:
            c = ClipRow(self, self.items[len(self.cards)], self.row_h)
            self.cards.append(c)
            self.list.insertWidget(self.list.count() - 1, c)     # above the stretch

    def _near_end(self, *_):
        if len(self.cards) >= len(self.items):
            return
        sb = self.scroll.verticalScrollBar()
        if sb.maximum() - sb.value() < 3 * (self.row_h + 8):
            self._more(len(self.cards) + self.BATCH)

    def select(self, i, scroll=True):
        if not self.cards:
            return
        if i >= len(self.cards):
            self._more(i + self.BATCH)             # arrowing past the built rows
        i = max(0, min(i, len(self.cards) - 1))
        for k, c in enumerate(self.cards):
            c.set_selected(k == i and self.hasFocus())
        self.sel = i
        if scroll:
            self.scroll.ensureWidgetVisible(self.cards[i], 0, 8)

    def focusInEvent(self, ev):
        self.select(self.sel, scroll=False); super().focusInEvent(ev)

    def focusOutEvent(self, ev):
        for c in self.cards:
            c.set_selected(False)
        super().focusOutEvent(ev)

    def toggle_row(self, row):
        for r in self.cards:
            if r is not row:
                r.set_open(False)
        row.set_open(not row.opened)
        if row in self.cards:
            self.select(self.cards.index(row), scroll=False)
        self.setFocus()

    def close_rows(self):
        for r in self.cards:
            r.set_open(False)

    def eventFilter(self, obj, ev):
        if obj is self.inner and ev.type() == QEvent.Type.MouseButtonPress:
            self.close_rows()
        return super().eventFilter(obj, ev)

    def activate(self, it, via, plain=False):
        self.picker.insert_clip_item(it, via, plain=plain)

    def keyPressEvent(self, ev):
        k = ev.key()
        if k == Qt.Key.Key_Down:
            self.select(self.sel + 1)
        elif k == Qt.Key.Key_Up:
            self.select(self.sel - 1)
        elif k in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.cards:
            plain = bool(ev.modifiers() & Qt.KeyboardModifier.ShiftModifier)   # Shift+Enter: as text
            self.activate(self.cards[self.sel].it, via="keyboard", plain=plain)
        elif k == Qt.Key.Key_Delete and self.cards:
            self.picker.delete_clip_item(self.cards[self.sel].it)
        elif k == Qt.Key.Key_P and ev.modifiers() == Qt.KeyboardModifier.ControlModifier and self.cards:
            it = self.cards[self.sel].it
            self.store.unpin(it) if it.pinned else self.store.pin(it)
        elif k == Qt.Key.Key_Menu and self.cards:
            self.toggle_row(self.cards[self.sel])
        else:
            super().keyPressEvent(ev)


# ------------------------------------------------------------------ theme ---
class Theme:
    def __init__(self, pal):
        dark = pal.window().color().lightness() < 128
        self.dark = dark
        self.accent = pal.highlight().color()
        if dark:
            self.bg = QColor(40, 40, 42); self.border = QColor(70, 70, 74)
            self.text = QColor(235, 235, 235); self.sub = QColor(170, 170, 175)
            self.hover = QColor(255, 255, 255, 22); self.field = QColor(28, 28, 30)
            self.tile = QColor(255, 255, 255, 16); self.tile_hover = QColor(255, 255, 255, 34)
        else:
            self.bg = QColor(249, 249, 249); self.border = QColor(210, 210, 214)
            self.text = QColor(25, 25, 25); self.sub = QColor(95, 95, 100)
            self.hover = QColor(0, 0, 0, 16); self.field = QColor(255, 255, 255)
            self.tile = QColor(0, 0, 0, 12); self.tile_hover = QColor(0, 0, 0, 26)



# ----------------------------------------------------------- kaomoji data --
KAOMOJI = [
    ("Happy", ["(◕‿◕)", "(｡◕‿◕｡)", "(＾▽＾)", "(≧▽≦)", "ヽ(・∀・)ﾉ", "(✿◠‿◠)", "(◠‿◠)", "٩(◕‿◕｡)۶",
               "(ﾉ◕ヮ◕)ﾉ*:･ﾟ✧", "＼(^o^)／", "(*^▽^*)", "(^_^)", "(^▽^)", "o(≧▽≦)o", "ᕕ( ᐛ )ᕗ",
               "(•‿•)", "( ˘▽˘)っ", "(´▽`)"]),
    ("Greeting", ["(^_^)/", "(・_・)ノ", "ヾ(・ω・*)ノ", "(｡･ω･)ﾉﾞ", "( ´ ▽ ` )ﾉ", "(*・ω・)ﾉ", "(^-^*)/",
                  "ヾ(＾∇＾)"]),
    ("Hugging", ["(っ´▽`)っ", "⊂(◉‿◉)つ", "(づ｡◕‿‿◕｡)づ", "(つ≧▽≦)つ", "⊂(・ω・*⊂)", "(づ￣ ³￣)づ"]),
    ("Winking", ["(^_-)", "(^_-)-☆", "(。•̀ᴗ-)✧", "☆⌒(ゝ。∂)", "(^_~)", "(^_<)〜☆"]),
    ("Love", ["(♥ω♥*)", "(◍•ᴗ•◍)❤", "(´∀｀)♡", "(｡♥‿♥｡)", "(✿ ♥‿♥)", "( ˘ ³˘)♥", "(*˘︶˘*).｡*♡",
              "(´ε｀ )♡", "(っ˘з(˘⌣˘ )"]),
    ("Sad", ["(╥﹏╥)", "(ಥ﹏ಥ)", "(T_T)", "(｡•́︿•̀｡)", "(ノ_<。)", "(´；ω；`)", "｡ﾟ･ (>﹏<) ･ﾟ｡",
             "(っ˘̩╭╮˘̩)っ", "(-_-。)", "(ᗒᗣᗕ)՞"]),
    ("Angry", ["(╬ Ò﹏Ó)", "(ง'̀-'́)ง", "ヽ(`Д´)ﾉ", "(｀ε´)", "(ಠ_ಠ)", "(¬_¬)", "٩(╬ʘ益ʘ╬)۶",
               "(ﾉಠ益ಠ)ﾉ", "(＃`Д´)"]),
    ("Surprised", ["(⊙_⊙)", "(°ロ°)", "Σ(°△°|||)", "(O_O)", "(ﾟДﾟ)", "w(°ｏ°)w", "ヽ(°〇°)ﾉ",
                   "(◎_◎;)", "(ʘᗩʘ')"]),
    ("Embarrassed", ["(^_^;)", "(￣▽￣;)", "(⌒_⌒;)", "(・_・;)", "(*/ω＼)", "(〃▽〃)", "(⁄ ⁄•⁄ω⁄•⁄ ⁄)",
                     "(//▽//)"]),
    ("Confused", ["¯\\_(ツ)_/¯", "┐(￣ヘ￣)┌", "╮(╯_╰)╭", "(・・ ) ?", "(・_・ヾ", "(・ω・)?", "(￢_￢)",
                  "(⊙_☉)"]),
    ("Sleepy", ["(－_－) zzZ", "(∪｡∪)｡｡｡zzZ", "(￣o￣) zzZZzzZZ", "(＿ ＿*) Z z z", "(-.-)Zzz"]),
    ("Cool", ["(⌐■_■)", "( •_•)>⌐■-■", "(☞ﾟヮﾟ)☞", "☜(ﾟヮﾟ☜)", "ᕦ(ò_óˇ)ᕤ", "( ͡° ͜ʖ ͡°)", "ಠ‿ಠ",
              "(ง •̀_•́)ง"]),
    ("Dancing", ["♪(┌・。・)┌", "ヾ(⌐■_■)ノ♪", "┏(・o・)┛♪", "＼(ﾟｰﾟ＼)", "(ﾉ≧∀≦)ﾉ", "(~˘▽˘)~",
                 "~(˘▽˘~)", "♪～(´ε｀ )"]),
    ("Table flip", ["(╯°□°)╯︵ ┻━┻", "┬─┬ノ( º _ ºノ)", "(ノಠ益ಠ)ノ彡┻━┻", "┻━┻ ︵ヽ(`Д´)ﾉ︵ ┻━┻",
                    "(╯‵□′)╯︵┻━┻"]),
    ("Animals", ["ʕ•ᴥ•ʔ", "(=^･ω･^=)", "(=①ω①=)", "ฅ^•ﻌ•^ฅ", "U・ᴥ・U", "(ᵔᴥᵔ)", "ʕ ·(エ)· ʔ",
                 "(・⊝・)", ">°))))彡", "くコ:彡", "(°)#))<<", "~>°)～～～"]),
]


def build_symbols(emoji_bases):
    """Symbol sections generated from Unicode, with official names."""
    import unicodedata as ud

    def rng(a, b, skip=""):
        return [chr(c) for c in range(a, b + 1) if ud.name(chr(c), "") and chr(c) not in skip]

    sets = [
        ("General punctuation", list("«»‹›“”‘’„‚–—…•·¡¿§¶†‡‰′″‴‼⁇⁈⁉‽⁂※¦¨¯´¸°~^`|")),
        ("Currency", list("$¢£¤¥") + rng(0x20A0, 0x20C0)),
        ("Latin", rng(0xC0, 0xFF, "×÷") + rng(0x100, 0x17F)),
        ("Math", list("±×÷≠≈≡≤≥∞√∛∜∑∏∫∬∮∂∆∇∈∉∋∩∪⊂⊃⊆⊇⊕⊗∧∨¬∀∃∄∅∝∠∡⊥∥∼≅≃⌊⌋⌈⌉"
                      "½⅓⅔¼¾⅕⅙⅛⅜⅝⅞⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿ₀₁₂₃₄₅₆₇₈₉")),
        ("Arrows", rng(0x2190, 0x21FF)),
        ("Geometric", rng(0x25A0, 0x25FF)),
        ("Other symbols", list("©®™℠℗№℃℉℮★☆✓✔✗✘☐☑☒♠♣♥♦♤♧♡♢♪♫♬♭♮♯☀☁☂☃☄☎☏✉✎✏✂⌘⌥⇧⏎⌫⌦⇥⎋"
                               "☯☮✝☪☸✡☢☣⚠⚡❄❤❥❦❧✦✧✩✪✫✬✭✮✯✰❖")),
        ("Greek", rng(0x391, 0x3A9) + rng(0x3B1, 0x3C9)),
        ("Cyrillic", rng(0x410, 0x44F)),
    ]
    out = []
    for title, chars in sets:
        items = []
        for c in dict.fromkeys(chars):
            name = ud.name(c, "").lower()
            # symbols that also exist as colour emoji: ask for the plain text look
            shown = c + "︎" if (c in emoji_bases or c + "️" in emoji_bases) else c
            items.append((shown, name[:1].upper() + name[1:]))
        out.append((title, items))
    return out


# ------------------------------------------------------------------- grid ---
class EmojiGrid(QWidget):
    def __init__(self, picker):
        super().__init__()
        self.picker = picker
        self.setMouseTracking(True)
        self.sections = []   # (title, [(display, name, base)]), as laid out
        self.all_sections = []
        self.row_caps = {}   # section index -> most rows it may take
        self.pos = []        # flat list of (QRectF, item)
        self.section_tops = []
        self.hover = -1
        self.sel = -1
        self.efont = QFont(EMOJI_FONT)
        self.efont.setPixelSize(EMOJI_PX)
        self.hfont = QFont(self.font())
        self.hfont.setWeight(QFont.Weight.DemiBold)
        # header height follows the real font size, so big system fonts can't overlap
        self.header_h = QFontMetrics(self.hfont).height() + 16

    def set_sections(self, sections, row_caps=None):
        """row_caps: {section index: rows}. Applied in relayout, at the grid's real
        width; counting items before the grid is laid out (its width is still
        Qt's default 640 then) let "Recently used" spill past its rows."""
        self.all_sections, self.row_caps = sections, row_caps or {}
        self.hover = -1
        self.sel = 0 if any(s[1] for s in sections) else -1
        self.relayout()

    SCROLLBAR = 10   # room kept free on the right for the thin scrollbar

    def cols(self):
        return max(COLS_MIN, (self.width() - self.SCROLLBAR) // CELL)

    def cell_w(self):
        # stretch cells to fill the width exactly, so there is no dead margin
        return (self.width() - self.SCROLLBAR) / self.cols()

    def x0(self):
        return 0

    def relayout(self):
        cols, x0, cw = self.cols(), self.x0(), self.cell_w()
        self.sections = [(t, items[:self.row_caps[k] * cols] if k in self.row_caps else items)
                         for k, (t, items) in enumerate(self.all_sections)]
        y = 0
        self.pos, self.section_tops = [], []
        for title, items in self.sections:
            self.section_tops.append(y)
            if not items:
                continue
            if title:
                y += self.header_h
            for i, it in enumerate(items):
                r, c = divmod(i, cols)
                self.pos.append((QRectF(x0 + c * cw, y + r * CELL, cw, CELL), it))
            y += ((len(items) + cols - 1) // cols) * CELL + 8
        self.sel = min(self.sel, len(self.pos) - 1)
        self.hover = min(self.hover, len(self.pos) - 1)
        self.setMinimumHeight(max(y, 10))
        self.update()

    def resizeEvent(self, ev):
        self.relayout()

    def item_at(self, p):
        for i, (r, _) in enumerate(self.pos):
            if r.contains(p.x(), p.y()):
                return i
        return -1

    def paintEvent(self, ev):
        t = self.picker.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        clip = QRectF(ev.rect())
        x0 = self.x0()
        p.setFont(self.hfont)
        p.setPen(t.text)
        for (title, items), top in zip(self.sections, self.section_tops):
            if not (title and items):
                continue
            hr = QRectF(x0 + 8, top, self.width() - x0 - 16, self.header_h)
            if hr.intersects(clip):
                p.save(); p.setClipRect(hr)
                p.drawText(hr, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                           QFontMetrics(self.hfont).elidedText(title, Qt.TextElideMode.ElideRight, int(hr.width())))
                p.restore()
        if not self.pos:
            p.setPen(t.sub)
            p.drawText(QRectF(0, 20, self.width(), 40), Qt.AlignmentFlag.AlignCenter, "No emojis found")
        p.setFont(self.efont)
        for i, (r, it) in enumerate(self.pos):
            if not r.intersects(clip):
                continue
            if i == self.sel:
                p.setPen(Qt.PenStyle.NoPen); p.setBrush(t.hover)
                p.drawRoundedRect(r.adjusted(2, 2, -2, -2), 6, 6)
                p.setPen(QPen(t.accent, 2)); p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(r.adjusted(3, 3, -3, -3), 6, 6)
            elif i == self.hover:
                p.setPen(Qt.PenStyle.NoPen); p.setBrush(t.hover)
                p.drawRoundedRect(r.adjusted(2, 2, -2, -2), 6, 6)
            p.setPen(t.text)
            p.save(); p.setClipRect(r)
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, it[0])
            p.restore()

    def mouseMoveEvent(self, ev):
        i = self.item_at(ev.position())
        if i != self.hover:
            self.hover = i
            self.picker.show_info(self.pos[i][1] if i >= 0 else
                                  (self.pos[self.sel][1] if self.sel >= 0 else None))
            self.update()

    def leaveEvent(self, ev):
        self.hover = -1
        self.picker.show_info(self.pos[self.sel][1] if 0 <= self.sel < len(self.pos) else None)
        self.update()

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            i = self.item_at(ev.position())
            if i >= 0:
                self.sel = i
                self.update()
                self.picker.pick(self.pos[i][1], via="mouse")
        elif ev.button() == Qt.MouseButton.RightButton:
            i = self.item_at(ev.position())
            if i >= 0:
                self.picker.remove_recent(i)       # right-click a recent emoji: forget it

    def move_sel(self, key):
        if not self.pos:
            return
        if self.sel < 0:
            self.sel = 0
        else:
            cur = self.pos[self.sel][0]
            if key == Qt.Key.Key_Left:
                self.sel = max(0, self.sel - 1)
            elif key == Qt.Key.Key_Right:
                self.sel = min(len(self.pos) - 1, self.sel + 1)
            else:
                up = key == Qt.Key.Key_Up
                cands = [(i, r) for i, (r, _) in enumerate(self.pos)
                         if (r.top() < cur.top() - 1 if up else r.top() > cur.top() + 1)]
                if cands:
                    ty = max(r.top() for _, r in cands) if up else min(r.top() for _, r in cands)
                    row = [(i, r) for i, r in cands if abs(r.top() - ty) < 1]
                    self.sel = min(row, key=lambda ir: abs(ir[1].left() - cur.left()))[0]
        r = self.pos[self.sel][0]
        self.picker.scroll.ensureVisible(int(r.center().x()), int(r.center().y()), 0, int(CELL * 0.8))
        self.picker.show_info(self.pos[self.sel][1])
        self.update()



class TextGrid(QWidget):
    """Grid of text items (symbols, or kaomoji of different widths) with section headers."""

    def __init__(self, picker, px, fixed=True, cell_h=44):
        super().__init__()
        self.picker, self.fixed, self.cell_h = picker, fixed, cell_h
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.font_ = QFont(self.font()); self.font_.setPixelSize(px)
        self.fm = QFontMetrics(self.font_)
        self.hfont = QFont(self.font()); self.hfont.setWeight(QFont.Weight.DemiBold)
        self.header_h = QFontMetrics(self.hfont).height() + 16
        self.sections, self.pos, self.section_tops = [], [], []
        self.hover = self.sel = -1
        self.on_pick = None
        self.info = None

    def set_sections(self, sections):
        self.sections = sections
        self.hover = -1
        self.sel = 0 if any(s[1] for s in sections) else -1
        self.relayout()

    def relayout(self):
        W = max(120, self.width() - 10)
        y = 0
        self.pos, self.section_tops = [], []
        for title, items in self.sections:
            self.section_tops.append(y)
            if not items:
                continue
            y += self.header_h
            if self.fixed:
                cols = max(7, W // 44); cw = W / cols
                for i, it in enumerate(items):
                    r, c = divmod(i, cols)
                    self.pos.append((QRectF(c * cw, y + r * self.cell_h, cw, self.cell_h), it))
                y += ((len(items) + cols - 1) // cols) * self.cell_h + 8
            else:
                unit = W / 3                 # kaomoji take 1, 2 or 3 columns, like Windows
                col = 0
                for it in items:
                    span = min(3, max(1, math.ceil((self.fm.horizontalAdvance(it[0]) + 22) / unit)))
                    if col + span > 3:
                        col = 0; y += self.cell_h
                    self.pos.append((QRectF(col * unit, y, span * unit, self.cell_h), it))
                    col += span
                y += self.cell_h + 8
        self.setMinimumHeight(max(y, 10))
        self.update()

    def resizeEvent(self, ev):
        self.relayout()

    def item_at(self, p):
        for i, (r, _) in enumerate(self.pos):
            if r.contains(p.x(), p.y()):
                return i
        return -1

    def paintEvent(self, ev):
        t = self.picker.theme
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        clip = QRectF(ev.rect())
        p.setFont(self.hfont); p.setPen(t.text)
        for (title, items), top in zip(self.sections, self.section_tops):
            if title and items:
                hr = QRectF(8, top, self.width() - 16, self.header_h)
                if hr.intersects(clip):
                    p.drawText(hr, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, title)
        p.setFont(self.font_)
        for i, (r, it) in enumerate(self.pos):
            if not r.intersects(clip):
                continue
            box = r.adjusted(2.5, 2.5, -2.5, -2.5)          # small gap between tiles
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(t.tile_hover if i == self.hover else t.tile)
            p.drawRoundedRect(box, 9, 9)
            if i == self.sel and self.hasFocus():
                p.setPen(QPen(t.accent, 2)); p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(box.adjusted(1, 1, -1, -1), 8, 8)
            p.setPen(t.text)
            p.drawText(r, Qt.AlignmentFlag.AlignCenter,
                       self.fm.elidedText(it[0], Qt.TextElideMode.ElideRight, int(r.width() - 8)))

    def _info(self, i):
        if self.info is not None:
            self.info.setText(self.pos[i][1][1] if 0 <= i < len(self.pos) else "")

    def mouseMoveEvent(self, ev):
        i = self.item_at(ev.position())
        if i != self.hover:
            self.hover = i
            self._info(i if i >= 0 else self.sel)
            self.update()

    def leaveEvent(self, ev):
        self.hover = -1; self._info(self.sel); self.update()

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            i = self.item_at(ev.position())
            if i >= 0 and self.on_pick:
                self.sel = i; self.update()
                self.on_pick(self.pos[i][1][0], "mouse")

    def keyPressEvent(self, ev):
        k = ev.key()
        if k in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down) and self.pos:
            self.move_sel(k)
        elif k in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and 0 <= self.sel < len(self.pos) and self.on_pick:
            self.on_pick(self.pos[self.sel][1][0], "keyboard")
        else:
            super().keyPressEvent(ev)

    def move_sel(self, key):
        if self.sel < 0:
            self.sel = 0
        else:
            cur = self.pos[self.sel][0]
            if key == Qt.Key.Key_Left:
                self.sel = max(0, self.sel - 1)
            elif key == Qt.Key.Key_Right:
                self.sel = min(len(self.pos) - 1, self.sel + 1)
            else:
                up = key == Qt.Key.Key_Up
                cands = [(i, r) for i, (r, _) in enumerate(self.pos)
                         if (r.top() < cur.top() - 1 if up else r.top() > cur.top() + 1)]
                if cands:
                    ty = max(r.top() for _, r in cands) if up else min(r.top() for _, r in cands)
                    row = [(i, r) for i, r in cands if abs(r.top() - ty) < 1]
                    self.sel = min(row, key=lambda ir: abs(ir[1].center().x() - cur.center().x()))[0]
        r = self.pos[self.sel][0]
        self.scroll.ensureVisible(int(r.center().x()), int(r.center().y()), 0, int(self.cell_h * 0.8))
        self._info(self.sel)
        self.update()


class ChipBar(QScrollArea):
    """A row of category chips you can scroll sideways with the mouse wheel."""

    def __init__(self, names, on_click):
        super().__init__()
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setWidgetResizable(True)
        inner = QWidget(); row = QHBoxLayout(inner)
        row.setContentsMargins(2, 0, 2, 0); row.setSpacing(4)
        self.group = QButtonGroup(self); self.group.setExclusive(True)
        self.chips = []
        for i, name in enumerate(names):
            b = QToolButton(); b.setText(name); b.setCheckable(True); b.setObjectName("chip")
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus); b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, i=i: on_click(i))
            self.group.addButton(b); self.chips.append(b); row.addWidget(b)
        row.addStretch()
        self.setWidget(inner)
        self.setFixedHeight(inner.sizeHint().height() + 6)

    def wheelEvent(self, ev):
        d = ev.angleDelta()
        step = d.y() if abs(d.y()) > abs(d.x()) else d.x()
        sb = self.horizontalScrollBar()
        sb.setValue(sb.value() - step)
        ev.accept()

    def set_current(self, i):
        if 0 <= i < len(self.chips) and not self.chips[i].isChecked():
            self.chips[i].setChecked(True)
            self.ensureWidgetVisible(self.chips[i], 24, 0)


class TextPage(QWidget):
    """A scrolling TextGrid with a "Recently used" row and a footer, for kaomoji or symbols."""

    def __init__(self, picker, key, sections, px, fixed):
        super().__init__()
        self.picker, self.key, self.base = picker, key, sections
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 4, 0, 0); lay.setSpacing(4)
        self.chips = ChipBar(["Recent"] + [t for t, _ in sections], self.goto)
        lay.addWidget(self.chips)
        self.grid = TextGrid(picker, px, fixed, 44 if fixed else 40)
        self.scroll = QScrollArea(); self.scroll.setWidget(self.grid); self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.grid.scroll = self.scroll
        self.scroll.verticalScrollBar().valueChanged.connect(self.sync_chip)
        lay.addWidget(self.scroll, 1)
        self.info = QLabel(); self.info.setContentsMargins(6, 0, 6, 0)
        lay.addWidget(self.info)
        self.grid.info = self.info
        self.grid.on_pick = lambda text, via: picker.pick_text(text, via, key)
        self.names = {t: n for _, items in sections for t, n in items}

    def refresh(self):
        recent = [(t, self.names.get(t, "")) for t in self.picker.conf.get(self.key, []) if t in self.names]
        self.grid.set_sections([("Recently used", recent)] + list(self.base))
        self.chips.chips[0].setEnabled(bool(recent))
        self.scroll.verticalScrollBar().setValue(0)
        self.sync_chip()
        self.grid._info(self.grid.sel)

    def goto(self, i):
        """Jump to a category, like the emoji tabs."""
        tops = self.grid.section_tops
        if i < len(tops):
            self.scroll.verticalScrollBar().setValue(tops[i])
            first = sum(len(sec[1]) for sec in self.grid.sections[:i])
            if first < len(self.grid.pos) and self.grid.sections[i][1]:
                self.grid.sel = first
                self.grid._info(first)
                self.grid.update()
        self.chips.set_current(i)
        self.chips.ensureWidgetVisible(self.chips.chips[i], 24, 0)
        self.grid.setFocus()

    def sync_chip(self, *_):
        sb = self.scroll.verticalScrollBar()
        y = sb.value() + 8
        k = None
        for i, top in enumerate(self.grid.section_tops):
            if top <= y and self.grid.sections[i][1]:
                k = i
        if sb.value() >= sb.maximum() and sb.maximum() > 0:
            k = len(self.grid.sections) - 1
        if k is None:
            k = next((i for i, sec in enumerate(self.grid.sections) if sec[1]), 0)
        self.chips.set_current(k)

# ----------------------------------------------------------------- window ---
class Header(QWidget):
    """Drag handle + settings + close, like the Windows picker."""

    def __init__(self, picker):
        super().__init__()
        self.picker = picker
        self.setFixedHeight(32)
        lay = QHBoxLayout(self); lay.setContentsMargins(2, 2, 2, 0); lay.setSpacing(2)
        self.back_btn = self._btn("back", "Back", picker.close_settings)
        self.title = QLabel("Settings"); self.title.setObjectName("settingsTitle")
        lay.addWidget(self.back_btn); lay.addWidget(self.title)
        lay.addStretch()
        self.gear_btn = self._btn("settings", "Settings", picker.open_settings)
        self.close_btn = self._btn("close", "Close", picker.hide)
        lay.addWidget(self.gear_btn); lay.addWidget(self.close_btn)
        self.set_settings_mode(False)

    def _btn(self, icon, tip, fn):
        b = QToolButton(); b.setIcon(svg_icon(icon, self.picker.theme.text.name(), 16))
        b.setIconSize(QSize(16, 16)); b.setAutoRaise(True); b.setFixedSize(30, 28)
        b.setToolTip(tip); b.setFocusPolicy(Qt.FocusPolicy.NoFocus); b.clicked.connect(fn)
        return b

    def set_settings_mode(self, on):
        self.back_btn.setVisible(on); self.title.setVisible(on); self.gear_btn.setVisible(not on)
        self.update()

    def paintEvent(self, ev):
        if self.back_btn.isVisible():
            return
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(self.picker.theme.sub)
        p.drawRoundedRect(QRectF(self.width() / 2 - 18, 13, 36, 4), 2, 2)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton and self.window().windowHandle():
            self.window().windowHandle().startSystemMove()


class SettingsPage(QScrollArea):
    def __init__(self, picker):
        super().__init__()
        self.picker = picker
        c = picker.conf
        self.setWidgetResizable(True); self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget(); self.setWidget(inner)
        inner.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        lay = QVBoxLayout(inner); lay.setContentsMargins(10, 6, 14, 10); lay.setSpacing(6)

        def heading(text):
            l = QLabel(text); l.setObjectName("heading"); lay.addSpacing(6); lay.addWidget(l)

        def indent(w):
            row = QHBoxLayout(); row.setContentsMargins(26, 0, 0, 0); row.addWidget(w); lay.addLayout(row)

        heading("Close the panel after inserting")
        self.close_mouse_cb = QCheckBox("When I click with the mouse")
        self.close_mouse_cb.setChecked(c["close_on_mouse"])
        self.close_kb_cb = QCheckBox("When I press Enter")
        self.close_kb_cb.setChecked(c["close_on_keyboard"])
        for cb_ in (self.close_mouse_cb, self.close_kb_cb):
            lay.addWidget(cb_); cb_.toggled.connect(self.save)
        hint = QLabel("Unchecked = the panel stays open so you can insert several.")
        hint.setWordWrap(True); lay.addWidget(hint)

        heading("Paste using")
        self.paste_group = QButtonGroup(self)
        self.paste_radios = {}
        for key, label in [("shift+insert", "Shift+Insert (works in terminals)"),
                           ("ctrl+v", "Ctrl+V"),
                           ("none", "Only copy, don't insert")]:
            rb = QRadioButton(label); rb.setChecked(c["paste_keys"] == key)
            self.paste_group.addButton(rb); self.paste_radios[key] = rb; lay.addWidget(rb)
            rb.toggled.connect(self.save)
        self.type_cb = QCheckBox("Type emoji instead of pasting (keeps formatting)")
        self.type_cb.setChecked(c.get("type_emoji", True))
        self.type_cb.setVisible(kwin_runtime_version() is not None)
        self.type_cb.toggled.connect(self.save)
        lay.addWidget(self.type_cb)
        self.ask_btn = QPushButton("Ask KDE for input permission again")
        self.ask_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.ask_btn.clicked.connect(lambda: (self.picker.paster.ask_again(), self.sync()))
        row = QHBoxLayout(); row.addWidget(self.ask_btn); row.addStretch(); lay.addLayout(row)
        self.ask_btn.setVisible(False)

        heading("Open the panel")
        self.place_group = QButtonGroup(self)
        self.place_radios = {}
        for key, label in [("caret", "At the text cursor"),
                           ("mouse", "At the mouse pointer"),
                           ("window", "Middle of the app I'm typing in"),
                           ("center", "Middle of the screen"),
                           ("remember", "Where I last moved it")]:
            rb = QRadioButton(label); rb.setChecked(c["placement"] == key)
            self.place_group.addButton(rb); self.place_radios[key] = rb; lay.addWidget(rb)
            rb.toggled.connect(self.save)
        ph = QLabel("Opens above the cursor or pointer, or below if there's no room. "
                    "Apps that don't share their text cursor use the pointer.")
        ph.setWordWrap(True); lay.addWidget(ph)

        heading("Clipboard history")
        self.hist_cb = QCheckBox("Remember what I copy")
        self.hist_cb.setChecked(c["clipboard_history"])
        self.hist_cb.toggled.connect(self.save)
        lay.addWidget(self.hist_cb)
        note = QLabel("Kept in memory only and forgotten when you log out. Pinned items "
                      "are saved on disk. Passwords are never recorded.")
        note.setWordWrap(True); lay.addWidget(note)

        heading("Recently used emojis")
        clr = QPushButton("Clear recent emojis"); clr.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        clr.clicked.connect(self.clear_recent)
        row = QHBoxLayout(); row.addWidget(clr); row.addStretch(); lay.addLayout(row)

        lay.addStretch()
        self.status = QLabel(); self.status.setWordWrap(True); lay.addWidget(self.status)
        self.sync()

    def sync(self):
        msgs = []
        pk = self.picker
        if pk.paster.error and pk.paster.error != "starting…":
            if pk.can_type():
                msgs.append("Pasting clipboard items is unavailable: " + pk.paster.error
                            + ". They are only copied. Emojis are still typed.")
            else:
                msgs.append("Auto-insert unavailable: " + pk.paster.error + ". Emojis are only copied.")
        self.ask_btn.setVisible(pk.paster.denied)
        stays_open = not (self.close_mouse_cb.isChecked() and self.close_kb_cb.isChecked())
        if stays_open and not pk.kwin_ok:
            msgs.append("KWin helper not running, so the panel will briefly flicker "
                        "when it stays open.")
        self.status.setText("\n".join(msgs))

    def save(self, *_):
        c = self.picker.conf
        c["close_on_mouse"] = self.close_mouse_cb.isChecked()
        c["close_on_keyboard"] = self.close_kb_cb.isChecked()
        c["type_emoji"] = self.type_cb.isChecked()
        c["paste_keys"] = next((k for k, rb in self.paste_radios.items() if rb.isChecked()), DEFAULT_CONF["paste_keys"])
        c["placement"] = next((k for k, rb in self.place_radios.items() if rb.isChecked()), DEFAULT_CONF["placement"])
        if c["placement"] == "caret" and not self.picker.kplug.active:
            self.picker._start_atspi()
        if c.get("clipboard_history") != self.hist_cb.isChecked():
            c["clipboard_history"] = self.hist_cb.isChecked()
            self.picker.set_history_enabled(c["clipboard_history"])
        save_conf(c)
        self.sync()

    def clear_recent(self):
        self.picker.conf["recent"] = []
        save_conf(self.picker.conf)
        self.status.setText("Recently used emojis cleared.")


class Picker(QWidget):
    def __init__(self, kwin_ok=False):
        super().__init__()
        self.conf = load_conf()
        self.theme = Theme(self.palette())
        self.paster = Paster()
        self.clip = ClipboardLender(self)
        self.kwin_ok = kwin_ok
        self.caret = None
        self.kplug = KwinCaretPlugin()
        self.kplug.activeChanged.connect(self._kplug_changed)
        self.kplug.clickedOutside.connect(self.on_click_outside)
        self.kplug.escapePressed.connect(self.on_escape_anywhere)
        self.kplug.panelClicked.connect(self.on_panel_click)
        self._click_target = None
        self.kplug.ensure()
        if not self.kplug.active:
            self._start_atspi()
        self.efont = QFont(EMOJI_FONT); self.efont.setPixelSize(EMOJI_PX)
        self.efm = QFontMetrics(self.efont)
        self._fit_cache = {}
        self.groups = self.load_data()
        self.search_index = [(it, (it[1] + " " + it[2]).lower())
                             for _, items in self.groups for it in items]
        self.by_base = {it[0]: it for _, items in self.groups for it in items}
        self.was_active = False
        self.busy = False        # True while focus is away for a stay-open paste
        self.title_n = 0
        self.searching = False
        self._spot = None
        self._wl_next, self._wl_pending, self._wl_proc = None, False, None
        self._wl_timer = QTimer(self); self._wl_timer.setSingleShot(True); self._wl_timer.setInterval(30)
        self._wl_timer.timeout.connect(self._wl_flush)
        self.pending_text = ""
        self._own_hide = False   # the panel hid itself for a moment to paste
        self.passive = False     # panel open, but your app keeps keyboard focus
        self.p_jobs = []         # mouse picks waiting to be pasted, in order
        self.p_running = False
        self.p_front_after = False
        self.cycling = False
        self.last_pick = 0.0
        self.cycle_text, self.cycle_gen = "", -1
        self.mode = "emoji"
        self.shown_at = 0.0
        self.store = ClipStore()
        self.watcher = ClipWatcher(self.store)
        if self.conf["clipboard_history"]:
            self.watcher.start()

        self.setWindowTitle("Kaomi")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(372, 480)

        t = self.theme
        root = QVBoxLayout(self); root.setContentsMargins(8, 2, 8, 8); root.setSpacing(4)
        self.header = Header(self)
        root.addWidget(self.header)

        # top row: Emoji | Clipboard (like Windows' Win+. panel)
        self.mode_row = QWidget(); mr = QHBoxLayout(self.mode_row)
        mr.setContentsMargins(2, 0, 0, 0); mr.setSpacing(4)
        self.mode_group = QButtonGroup(self); self.mode_btns = {}
        for key, icon, tip in [("emoji", "smileys", "Emoji"), ("kaomoji", "kaomoji", "Kaomoji"),
                               ("symbols", "symbols", "Symbols"), ("clipboard", "clipboard", "Clipboard history")]:
            b = QToolButton(); b.setCheckable(True); b.setAutoRaise(True); b.setObjectName("mode")
            b.setFixedSize(42, 38); b.setIconSize(QSize(22, 22)); b.setToolTip(tip)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b._icons = (svg_icon(icon, t.text.name(), 22), svg_icon(icon, t.accent.name(), 22))
            b.setIcon(b._icons[0])
            b.toggled.connect(lambda on, b=b: b.setIcon(b._icons[1 if on else 0]))
            b.clicked.connect(lambda _=False, k=key: self.set_mode(k))
            self.mode_group.addButton(b); self.mode_btns[key] = b; mr.addWidget(b)
        mr.addStretch()
        root.addWidget(self.mode_row)
        line = QFrame(); line.setObjectName("sep"); line.setFixedHeight(1)
        self.mode_sep = line
        root.addWidget(line)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        main = QWidget(); ml = QVBoxLayout(main); ml.setContentsMargins(0, 0, 0, 0); ml.setSpacing(6)
        self.stack.addWidget(main)

        # category tabs (outline icons, like Windows)
        tabs = QHBoxLayout(); tabs.setSpacing(0)
        self.tab_group = QButtonGroup(self); self.tab_group.setExclusive(True)
        self.tabs = []
        tips = ["Recently used"] + [g[0] for g in self.groups]
        for i, key in enumerate(TAB_KEYS):
            b = QToolButton(); b.setCheckable(True); b.setAutoRaise(True); b.setObjectName("cat")
            b.setFixedSize(30, 30); b.setIconSize(QSize(18, 18)); b.setToolTip(tips[i])
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b._icons = (svg_icon(key, t.sub.name(), 18), svg_icon(key, t.accent.name(), 18))
            b.setIcon(b._icons[0])
            b.toggled.connect(lambda on, b=b: b.setIcon(b._icons[1 if on else 0]))
            b.clicked.connect(lambda _=False, k=i: self.goto_tab(k))
            self.tab_group.addButton(b); self.tabs.append(b); tabs.addWidget(b)
        tabs.addStretch()
        self.tone_btn = QToolButton(); self.tone_btn.setAutoRaise(True)
        self.tone_btn.setFixedSize(30, 30); self.tone_btn.setIconSize(QSize(18, 18))
        self.tone_btn.setToolTip("Skin tone"); self.tone_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.tone_btn.setObjectName("tone")
        self.tone_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.tone_btn)
        for k in range(6):
            a = QAction(swatch_icon(TONE_COLORS[k]), TONE_NAMES[k], menu)
            a.triggered.connect(lambda _=False, k=k: self.set_tone(k))
            menu.addAction(a)
        self.tone_btn.setMenu(menu)
        self._menu_closed_at = 0.0
        menu.aboutToHide.connect(lambda: setattr(self, "_menu_closed_at", time.monotonic()))
        tabs.addWidget(self.tone_btn)
        ml.addLayout(tabs)

        # search
        self.search = QLineEdit(); self.search.setPlaceholderText("Search emojis")
        self.search.addAction(svg_icon("search", t.sub.name(), 16), QLineEdit.ActionPosition.LeadingPosition)
        self.search.setClearButtonEnabled(True); self.search.setFixedHeight(34)
        self.search.textChanged.connect(self.refresh)
        self.search.installEventFilter(self)
        ml.addWidget(self.search)

        # grid
        self.grid = EmojiGrid(self)
        self.scroll = QScrollArea(); self.scroll.setWidget(self.grid); self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.scroll.verticalScrollBar().valueChanged.connect(self.sync_tab)
        ml.addWidget(self.scroll, 1)

        # footer: big preview + name
        foot = QHBoxLayout(); foot.setContentsMargins(4, 0, 4, 0)
        self.prev = QLabel(); pf = QFont(EMOJI_FONT); pf.setPixelSize(24); self.prev.setFont(pf)
        self.prev.setFixedWidth(36)
        self.info = QLabel()
        foot.addWidget(self.prev); foot.addWidget(self.info, 1)
        ml.addLayout(foot)

        self.emoji_page = main
        self.kao_page = TextPage(self, "recent_kaomoji", [(t, [(k, t) for k in items]) for t, items in KAOMOJI], 15, fixed=False)
        self.stack.addWidget(self.kao_page)
        self.sym_page = TextPage(self, "recent_symbols", build_symbols(set(self.by_base)), 21, fixed=True)
        self.stack.addWidget(self.sym_page)
        self.clip_page = ClipboardPage(self, self.store)
        self.stack.addWidget(self.clip_page)
        self.settings = SettingsPage(self)
        self.stack.addWidget(self.settings)

        hov = '255,255,255,0.09' if t.dark else '0,0,0,0.06'
        acc = f"{t.accent.red()},{t.accent.green()},{t.accent.blue()}"
        tile = f"{t.tile.red()},{t.tile.green()},{t.tile.blue()},{t.tile.alphaF():.3f}"
        tile_h = f"{t.tile_hover.red()},{t.tile_hover.green()},{t.tile_hover.blue()},{t.tile_hover.alphaF():.3f}"
        self.setStyleSheet(f"""
            QLineEdit {{ background:{t.field.name()}; color:{t.text.name()};
                border:1px solid {t.border.name()}; border-bottom:2px solid {t.accent.name()};
                border-radius:6px; padding:0 4px; }}
            QToolButton {{ color:{t.text.name()}; border:none; border-radius:6px; background:transparent; }}
            QToolButton:hover {{ background:rgba({hov}); }}
            QToolButton#mode:checked {{ border-bottom:2px solid {t.accent.name()};
                border-bottom-left-radius:0; border-bottom-right-radius:0; }}
            QToolButton#cat:checked {{ background:rgba({acc},0.16); }}
            QFrame#sep {{ background:{t.border.name()}; }}
            QFrame#card {{ background:{t.field.name()}; border:1px solid {t.border.name()}; border-radius:8px; }}
            QFrame#card:hover {{ border-color:{t.sub.name()}; }}
            QFrame#card[sel="true"] {{ border:2px solid {t.accent.name()}; }}
            QLabel#cardText {{ color:{t.text.name()}; }}
            QToolButton#chip {{ padding:3px 10px; border-radius:10px; border:1px solid transparent; color:{t.sub.name()};
                background:rgba({tile}); }}
            QToolButton#chip:hover {{ color:{t.text.name()}; background:rgba({tile_h}); }}
            QToolButton#chip:checked {{ background:rgba({acc},0.28); color:{t.text.name()}; }}
            QToolButton#chip:disabled {{ color:{t.border.name()}; background:rgba({tile}); }}
            QToolButton#action {{ background:{t.field.name()}; border:1px solid {t.border.name()}; border-radius:8px; }}
            QToolButton#action:hover {{ border-color:{t.sub.name()}; background:rgba({hov}); }}
            QToolButton#action:disabled {{ background:transparent; }}
            QToolButton::menu-indicator {{ image:none; width:0; }}
            QLabel {{ color:{t.sub.name()}; }}
            QLabel#heading, QLabel#settingsTitle {{ color:{t.text.name()}; font-weight:600; }}
            QCheckBox, QRadioButton {{ color:{t.text.name()}; spacing:8px; padding:2px 0; }}
            QCheckBox:disabled, QRadioButton:disabled {{ color:{t.sub.name()}; }}
            QPushButton {{ color:{t.text.name()}; background:rgba({hov}); border:1px solid {t.border.name()};
                border-radius:6px; padding:5px 12px; }}
            QPushButton:hover {{ border-color:{t.accent.name()}; }}
            QPushButton:disabled {{ color:{t.sub.name()}; }}
            QScrollArea, QScrollArea > QWidget > QWidget, QStackedWidget > QWidget {{ background:transparent; }}
            QScrollBar:vertical {{ background:transparent; width:8px; margin:2px; }}
            QScrollBar::handle:vertical {{ background:{t.sub.name()}; border-radius:2px; min-height:30px; }}
            QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ height:0; background:none; }}
            QMenu {{ background:{t.bg.name()}; color:{t.text.name()}; border:1px solid {t.border.name()}; padding:4px; }}
            QMenu::item {{ padding:5px 14px 5px 8px; border-radius:4px; }}
            QMenu::item:selected {{ background:{t.accent.name()}; color:white; }}
        """)
        self.update_tone_btn()
        self.refresh()
        self.set_mode("emoji")
        QGuiApplication.instance().applicationStateChanged.connect(self._app_state)

    def _start_atspi(self):
        """Fallback text-cursor source, only used when the KWin plugin isn't active."""
        if self.caret is None and self.conf.get("placement") == "caret":
            try:
                self.caret = CaretTracker()
            except Exception as ex:
                log(f"caret tracker failed: {ex}")

    def _kplug_changed(self, active):
        if active and self.caret is not None:
            self.caret.proc.kill()
            self.caret = None                 # the plugin covers every app
        elif not active:
            self._start_atspi()

    # ---- modes
    def in_settings(self):
        return self.stack.currentWidget() is self.settings

    def set_mode(self, mode):
        self.mode = mode
        self.mode_btns[mode].setChecked(True)
        if self.in_settings():
            self.header.set_settings_mode(False)
        self.mode_row.show(); self.mode_sep.show()
        if mode == "emoji":
            self.stack.setCurrentWidget(self.emoji_page)
        elif mode in ("kaomoji", "symbols"):
            page = self.kao_page if mode == "kaomoji" else self.sym_page
            self.stack.setCurrentWidget(page)
            page.refresh()
        else:
            self.stack.setCurrentWidget(self.clip_page)
            self.clip_page.rebuild()
            self.clip_page.sel = 0
            self.clip_page.select(0)
        self._focus_current()

    def _focus_current(self):
        {"emoji": self.search, "kaomoji": self.kao_page.grid, "symbols": self.sym_page.grid,
         "clipboard": self.clip_page}.get(self.mode, self.search).setFocus()

    def clip_status_message(self):
        if not self.conf["clipboard_history"]:
            return "Clipboard history is turned off.\nTurn it on in Settings."
        if self.watcher.error:
            return "Clipboard history needs " + self.watcher.error + ".\nRe-run the installer."
        return "Nothing here yet.\nCopy something and it will show up here."

    # ---- data
    def fits(self, text):
        """False if this font can't draw the emoji as one picture (older Noto versions)."""
        r = self._fit_cache.get(text)
        if r is None:
            ok = self.efm.horizontalAdvance(text) <= EMOJI_PX * 1.6
            if ok and len(text) == 1:
                ok = self.efm.inFontUcs4(ord(text))
            self._fit_cache[text] = r = ok
        return r

    def load_data(self):
        raw = json.loads(zlib.decompress(base64.b64decode(DATA)).decode())
        return [(name, [tuple(x) for x in items if self.fits(x[0])]) for name, items in raw]

    def recents(self):
        return [self.by_base[e] for e in self.conf["recent"] if e in self.by_base]

    def disp(self, it):
        if it[3] and self.conf["skin_tone"]:
            toned = apply_tone(it[0], self.conf["skin_tone"])
            if self.fits(toned):
                return (toned, it[1], it)
        return (it[0], it[1], it)

    # ---- views
    def refresh(self):
        q = self.search.text().strip().lower()
        if q:
            words = q.split()
            hits = []
            qs = self.search.text().strip().replace("\ufe0f", "")
            for it, hay in self.search_index:
                if it[0].replace("\ufe0f", "") == qs:          # typed/pasted the emoji itself
                    hits.append(((-1, 0), it))
                    continue
                if all(w in hay for w in words):
                    name = it[1].lower()
                    nw = name.split()
                    score = 0 if name == q else 0.5
                    for w in words:                      # every word counts, name words best
                        score += (0 if w in nw else 1 if any(n.startswith(w) for n in nw)
                                  else 2 if w in name else 3)
                    hits.append(((score, len(name)), it))
            hits.sort(key=lambda s: s[0])
            secs = [("", [self.disp(it) for _, it in hits])]
            self.tab_group.setExclusive(False)
            for b in self.tabs:
                b.setChecked(False)
            self.tab_group.setExclusive(True)
        else:
            secs = [("Recently used", [self.disp(it) for it in self.recents()])]
            secs += [(name, [self.disp(it) for it in items]) for name, items in self.groups]
            self.tabs[0].setEnabled(bool(secs[0][1]))
        self.searching = bool(q)
        self.grid.set_sections(secs, None if q else {0: RECENT_ROWS})
        self.scroll.verticalScrollBar().setValue(0)
        self.sync_tab()
        self.show_info(self.grid.pos[0][1] if self.grid.pos else None)

    def goto_tab(self, k):
        if self.searching:
            self.search.clear()
        top = self.grid.section_tops[k] if k < len(self.grid.section_tops) else 0
        self.scroll.verticalScrollBar().setValue(top)
        self.tabs[k].setChecked(True)
        before = sum(len(s[1]) for s in self.grid.sections[:k])
        if before < len(self.grid.pos) and self.grid.sections[k][1]:
            self.grid.sel = before
            self.show_info(self.grid.pos[before][1]); self.grid.update()
        self.search.setFocus()

    def sync_tab(self, *_):
        if self.searching or not self.grid.section_tops:
            return
        sb = self.scroll.verticalScrollBar()
        y = sb.value() + 8
        k = None
        for i, top in enumerate(self.grid.section_tops):
            if top <= y and self.grid.sections[i][1]:
                k = i
        if sb.value() >= sb.maximum() and sb.maximum() > 0:
            k = len(self.tabs) - 1
        if k is None:
            k = next((i for i, s in enumerate(self.grid.sections) if s[1]), 0)
        self.tabs[k].setChecked(True)

    def show_info(self, d):
        if d is None:
            self.prev.setText(""); self.info.setText("")
            return
        self.prev.setText(d[0])
        fm = QFontMetrics(self.info.font())
        self.info.setText(fm.elidedText(d[1][:1].upper() + d[1][1:], Qt.TextElideMode.ElideRight,
                                        max(80, self.info.width() - 4)))

    def set_tone(self, k):
        self.conf["skin_tone"] = k; save_conf(self.conf)
        self.update_tone_btn()
        v = self.scroll.verticalScrollBar().value()
        sel = self.grid.sel
        self.refresh()
        self.grid.sel = sel; self.scroll.verticalScrollBar().setValue(v)
        self.search.setFocus()

    def update_tone_btn(self):
        self.tone_btn.setIcon(swatch_icon(TONE_COLORS[self.conf["skin_tone"]], 18, self.theme.sub.name()))

    # ---- settings
    def open_settings(self):
        self.settings.sync()
        self.settings.verticalScrollBar().setValue(0)
        self.stack.setCurrentWidget(self.settings)
        self.mode_row.hide(); self.mode_sep.hide()
        self.header.set_settings_mode(True)
        self.settings.setFocus()

    def close_settings(self):
        self.header.set_settings_mode(False)
        self.refresh()
        self.set_mode(self.mode)

    def set_history_enabled(self, on):
        if on:
            self.watcher.start()
        else:
            self.watcher.stop()
            self.store.clear()

    # ---- picking
    def pick(self, d, via):
        text, it = d[0], d[2]
        rec = [e for e in self.conf["recent"] if e != it[0]]
        self.conf["recent"] = ([it[0]] + rec)[:32]
        save_conf(self.conf)
        self.insert_text(text, via)

    def remove_recent(self, i):
        """Drop grid item i from "Recently used" (a stray click shouldn't keep its spot)."""
        if self.searching or not self.grid.sections or i >= len(self.grid.sections[0][1]):
            return                                   # not a recent
        base = self.grid.pos[i][1][2][0]
        self.conf["recent"] = [e for e in self.conf["recent"] if e != base]
        save_conf(self.conf)
        log(f"recent removed: {base}")
        v = self.scroll.verticalScrollBar().value()
        self.refresh()
        self.grid.sel = min(i, len(self.grid.pos) - 1)
        self.scroll.verticalScrollBar().setValue(v)
        if self.grid.sel >= 0:
            self.show_info(self.grid.pos[self.grid.sel][1])
        self.grid.update()

    def pick_text(self, text, via, recent_key):
        """Kaomoji / symbols: same instant insert as emoji, with their own recents."""
        rec = [e for e in self.conf.get(recent_key, []) if e != text]
        self.conf[recent_key] = ([text] + rec)[:24]
        save_conf(self.conf)
        self.insert_text(text, via)

    def insert_text(self, text, via):
        log(f"pick ({via}): " + ("type" if self.can_type() else "paste" if self.can_paste() else "copy only")
            + (", stay-open" if not self.conf["close_on_" + via] else "")
            + (", passive" if self.passive else ""))
        if not self.can_paste() and not self.can_type():
            QGuiApplication.clipboard().setText(text, QClipboard.Mode.Clipboard)
            self.after_copy_only(via, "Copied " + text)
            return
        # Borrow the clipboard invisibly: remember what was there, hand over the
        # emoji marked as "secret" (clipboard history skips it), paste, then put
        # the old contents back once the app has read the emoji.
        if self.conf["close_on_" + via] or not self.kwin_ok:
            self.insert(via, self._stage(text))
            return
        if via == "mouse" and self.can_be_passive():
            self._passive_add(("text", text))
            return
        # Panel stays open: batch fast picks. While one paste is in flight, new
        # picks queue up and go in together on the next round, so spamming never
        # makes the panel hide and reappear.
        self.pending_text += text
        self.last_pick = time.monotonic()
        if not self.cycling:
            self._cycle()

    def _cycle(self, waited=0):
        if not self.pending_text or not self.isVisible():
            self.cycling = False
            self._done_busy()
            return
        self.cycling = True
        self.busy = True
        if not self.isActiveWindow():
            # the clipboard can only be set from the focused window: wait for KWin
            # to hand focus back (it was asked with "front"); then fall back
            if waited < 200:
                if waited == 0:
                    self.signal_kwin("front")
                QTimer.singleShot(25, lambda: self._cycle(waited + 25))
                return
            text, self.pending_text = self.pending_text, ""
            typed = self._stage(text)
            log("focus didn't return to the picker; using hide/paste/return instead")
            self._hide_paste_return(self.conf, typed)
            QTimer.singleShot(int(self.conf["paste_delay_ms"]) + 450, self._cycle)
            return
        text, self.pending_text = self.pending_text, ""
        self.cycle_typed = self._stage(text)
        self.cycle_text, self.cycle_gen = text, self.clip.gen
        self.signal_kwin("back")                               # focus the app you're typing in
        QTimer.singleShot(int(self.conf["paste_delay_ms"]), lambda: self._cycle_paste(0))

    def _cycle_paste(self, tries):
        if not self.isVisible() and not self._own_hide:
            # you closed the panel mid-cycle (Escape, Meta+., a click elsewhere):
            # don't type into whatever has focus now; give the clipboard back
            self.cycling = self.busy = False
            self.clip.restore(self.cycle_gen)
            return
        if self.clip.gen != self.cycle_gen:
            # something else (a clipboard item) took the clipboard mid-cycle:
            # put this batch back in the queue instead of pasting the wrong thing
            self.pending_text = self.cycle_text + self.pending_text
            QTimer.singleShot(200, self._cycle)
            return
        if self.isActiveWindow():
            # a click landed on the panel mid-switch and took focus back: just ask
            # KWin again (the new emoji is already queued) - never hide for that
            if time.monotonic() - self.last_pick < 0.15:
                self.signal_kwin("back")
                QTimer.singleShot(30, lambda: self._cycle_paste(tries))
                return
            if tries < 4:
                self.signal_kwin("back")
                QTimer.singleShot(30, lambda: self._cycle_paste(tries + 1))
                return
            log("focus stayed on the picker; using hide/paste/return instead")
            self._hide_paste_return(self.conf, self.cycle_typed)
            QTimer.singleShot(int(self.conf["paste_delay_ms"]) + 450, self._cycle)
            return
        def after():
            QTimer.singleShot(60, lambda: self.signal_kwin("front"))  # focus the panel again
            QTimer.singleShot(110, self._cycle)                        # next batch, if any
        self._send_paste(self.conf["paste_keys"], after, self.cycle_typed)

    # ---- stay-open mouse picks: your app keeps keyboard focus the whole time, so
    # nothing flickers. Only possible when the KWin plugin reports clicks outside
    # the panel (a click into an app that already has focus is invisible otherwise).
    def can_be_passive(self):
        return self.kplug.active and self.kplug.clicks

    def _enter_passive(self):
        if not self.passive:
            self.passive = True
            self.kplug.set_passive(True)         # clicks on the panel no longer take focus
            self.signal_kwin("passive")          # KWin gives focus back to your app

    def _leave_passive(self):
        if not self.passive:
            return
        if self.p_running:
            self.p_front_after = True            # finish pasting what you clicked first
            return
        self.passive = False
        self.kplug.set_passive(False)
        self.signal_kwin("front")                # the panel takes focus (e.g. to type a search)

    def _passive_add(self, job):
        self._enter_passive()
        if job[0] == "text" and self.p_jobs and self.p_jobs[-1][0] == "text":
            self.p_jobs[-1] = ("text", self.p_jobs[-1][1] + job[1])   # fast clicks go in together
        else:
            self.p_jobs.append(job)
        if not self.p_running:
            self.p_running = True
            self._p_next(0)

    def _p_next(self, waited):
        """Paste the next queued pick. One at a time: the next emoji only goes on
        the clipboard after the app has read the previous one."""
        if not self.p_jobs or not self.isVisible():
            self.p_jobs, self.p_running = [], False
            if self.p_front_after:
                self.p_front_after = False
                self._leave_passive()
            return
        if self.isActiveWindow():
            # the hand-back to your app hasn't happened yet (first click, or a
            # click that is still being handed back): wait, never type into the panel
            if self.passive and waited < 400:
                QTimer.singleShot(15, lambda: self._p_next(waited + 15))
                return
            self._p_fallback()
            return
        job = self.p_jobs.pop(0)
        typed = None
        if job[0] == "text":
            typed = self._stage(job[1])
        else:
            _, it, plain = job
            self.clip.cancel()
            self.write_clipboard(snap_of_item(it, plain))
            cb = QGuiApplication.clipboard()
            if it.kind == "text" and cb.supportsSelection() and self.conf["paste_keys"] == "shift+insert":
                cb.setText(it.payload, QClipboard.Mode.Selection)
        gen = self.clip.gen
        QTimer.singleShot(int(self.conf["paste_delay_ms"]), lambda: self._p_paste(job, gen, 0, typed))

    def _p_paste(self, job, gen, waited, typed=None):
        if not self.isVisible():
            self.p_jobs, self.p_running = [], False
            self.clip.restore(gen)               # you closed the panel: don't type anywhere
            return
        if self.isActiveWindow():
            if self.passive and waited < 300:
                QTimer.singleShot(15, lambda: self._p_paste(job, gen, waited + 15, typed))
                return
            self.p_jobs.insert(0, job)
            self._p_fallback()
            return
        if gen != self.clip.gen:
            self.p_jobs.insert(0, job)           # the clipboard changed under us: redo this one
            QTimer.singleShot(20, lambda: self._p_next(0))
            return
        self._send_paste(self.conf["paste_keys"], lambda: self._p_wait(job, gen, 0), typed)

    def _p_fallback(self):
        """KWin didn't give focus back to your app: hide for a moment, paste, return
        (never type into the panel's own search box)."""
        jobs, self.p_jobs, self.p_running, self.p_front_after = self.p_jobs, [], False, False
        log("focus stayed on the picker; using hide/paste/return instead")
        if self.passive:
            self.passive = False
            self.kplug.set_passive(False)        # the plugin stops taking clicks on the panel
        text = "".join(j[1] for j in jobs if j[0] == "text")
        typed = None
        if text:
            typed = self._stage(text)
        elif jobs:
            _, it, plain = jobs[-1]
            self.clip.cancel()
            self.write_clipboard(snap_of_item(it, plain))
        else:
            return
        self._hide_paste_return(self.conf, typed)

    def _p_wait(self, job, gen, waited):
        # text: wait until the app has read the emoji; clipboard items: short pause
        typed = job[0] == "text" and self.can_type()          # keystrokes: nothing to wait for
        done = (typed and waited >= 20) or (job[0] == "text" and self.clip.read_gen == gen) \
            or waited >= (250 if job[0] == "text" else 120)
        if done:
            QTimer.singleShot(15, lambda: self._p_next(0))
        else:
            QTimer.singleShot(10, lambda: self._p_wait(job, gen, waited + 10))

    def on_click_outside(self, x, y):
        """The KWin plugin saw a click that wasn't on the panel: close it, like
        Windows. Works even when the click lands in the app that already has focus."""
        if QApplication.activePopupWidget() or time.monotonic() - self._menu_closed_at < 0.4:
            # the skin-tone menu is open (or just closed: KWin's report of the click
            # and the menu's own reaction to it can arrive in either order). It
            # sticks out past the panel, so this click is on it, or it just
            # closes the menu, like any menu.
            return
        if self.isVisible() and (self.was_active or self.passive or not self._just_opened()):
            log(f"close: click outside at {x},{y}")
            self.hide()

    def escape_action(self):
        """Escape closes the panel. Always; nothing in between."""
        self.hide()

    def on_panel_click(self, x, y, button, pressed):
        """Stay-open mode: the KWin plugin took a click on the panel, so KWin
        didn't activate it and your app kept focus. Deliver it to the widget
        under the pointer ourselves."""
        from PyQt6.QtGui import QMouseEvent
        if not self.isVisible():
            return
        pos = QPointF(x, y)
        if pressed:
            target = self.childAt(QPoint(x, y)) or self
            self._click_target = target
            wants_keys = target is self.search or self.search.isAncestorOf(target) \
                or target is self.header or self.header.isAncestorOf(target)
            if wants_keys:
                # typing a search / dragging the panel needs it focused: leave stay-open mode
                self._leave_passive()
                if target is self.header:
                    self._click_target = None    # a drag needs a real press; click again to drag
                    return
        else:
            target = self._click_target
            self._click_target = None
            if target is None:
                return
        try:
            local = QPointF(target.mapFrom(self, QPoint(x, y)))
        except RuntimeError:
            return                               # widget went away between press and release
        btn = Qt.MouseButton(button)
        ev = QMouseEvent(QEvent.Type.MouseButtonPress if pressed else QEvent.Type.MouseButtonRelease,
                         local, pos, btn, btn if pressed else Qt.MouseButton.NoButton,
                         Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(target, ev)

    def on_escape_anywhere(self):
        """The KWin plugin took an Escape press while the panel was open (no app
        got it, wherever the keyboard focus was)."""
        if self.isVisible():
            log("Escape (taken by KWin)")
            self.escape_action()

    def on_other_app(self):
        """KWin says you activated another app while the panel is open: close it
        (not in the middle of the panel's own paste, where focus moves on purpose)."""
        # always, whatever the stay-open settings say. Only ignored while the panel
        # is still opening and Qt hasn't seen it focused yet (focus can pass through
        # other windows for an instant then).
        if self.isVisible() and (self.was_active or self.passive or not self._just_opened()):
            self.hide()

    def _just_opened(self):
        """While the panel is still opening, focus can pass through other windows
        for an instant. That is not you clicking away."""
        return time.monotonic() - self.shown_at < 0.5

    def _app_state(self, state):
        # Qt-side fallback for the same thing: the whole app lost focus
        if state == Qt.ApplicationState.ApplicationInactive and self.isVisible() and self.was_active \
                and not self.busy and not self.passive and not QApplication.activePopupWidget():
            QTimer.singleShot(80, self._maybe_hide)

    def insert_clip_item(self, it, via, plain=False):
        """Clipboard history item: it becomes the current clipboard (like Windows).
        plain=True drops the formatting ("Paste as text")."""
        if via == "mouse" and self.kwin_ok and not self.conf["close_on_mouse"] and self.can_paste() \
                and self.can_be_passive():
            self._passive_add(("clip", it, plain))
            return
        self.clip.cancel()
        self.write_clipboard(snap_of_item(it, plain))
        cb = QGuiApplication.clipboard()
        if it.kind == "text" and cb.supportsSelection() and self.conf["paste_keys"] == "shift+insert":
            cb.setText(it.payload, QClipboard.Mode.Selection)
        if not self.can_paste():
            self.after_copy_only(via, "Copied to clipboard")
            return
        self.insert(via)

    # ---- every clipboard write the picker makes goes through here
    def write_clipboard(self, snap):
        """Put `snap` on the clipboard (None = empty it). Tagged as the picker's own,
        so the history watcher never records it as a new copy."""
        self.watcher.note_own_write(snap)
        cb = QGuiApplication.clipboard()
        if self.clip._can_set_directly():
            self._wl_drop_queued()
            if snap is None:
                cb.clear(QClipboard.Mode.Clipboard)
                return
            md = QMimeData()
            if snap.mime.startswith("text/plain"):
                md.setText(snap.data.decode("utf-8", errors="replace"))
                if snap.html:
                    md.setHtml(snap.html)
            else:
                md.setData(snap.mime, QByteArray(snap.data))
            for mime, data in snap.extra:
                if mime.startswith("text/plain"):
                    md.setText(data.decode("utf-8", errors="replace"))
                else:
                    md.setData(mime, QByteArray(data))
            md.setData(OWN_MARK, QByteArray(b"1"))
            cb.setMimeData(md, QClipboard.Mode.Clipboard)
            return
        # Wayland with the panel unfocused: only wl-copy may set the clipboard.
        # Writes are queued so that only the latest one wins, in order.
        self._wl_next, self._wl_pending = snap, True
        self._wl_timer.start()

    def _wl_drop_queued(self):
        """Forget a wl-copy write that hasn't started yet (something newer replaces it)."""
        self._wl_next, self._wl_pending = None, False
        self._wl_timer.stop()

    def _wl_flush(self):
        if not self._wl_pending or (self._wl_proc is not None
                                    and self._wl_proc.state() != QProcess.ProcessState.NotRunning):
            return                                   # runs again when the current one ends
        snap = self._wl_next
        tool, args, payload = copy_command(snap)
        if not tool or not os.environ.get("WAYLAND_DISPLAY"):
            self._wl_pending = False
            return
        self._wl_pending = False
        proc = QProcess(self)
        self._wl_proc = proc

        def done(*_):
            proc.deleteLater()
            if self._wl_proc is proc:
                self._wl_proc = None
            if self._wl_pending:
                QTimer.singleShot(60, self._wl_flush)
        proc.finished.connect(done)
        proc.errorOccurred.connect(lambda e: e == QProcess.ProcessError.FailedToStart and done())
        proc.start(tool, args)
        proc.write(QByteArray(payload)); proc.closeWriteChannel()

    def hand_over_clipboard(self):
        """On Wayland a program's clipboard data dies with it. If the picker is the
        one holding the clipboard (after a paste from history, say), hand the
        contents to a wl-copy process that outlives it."""
        cb = QGuiApplication.clipboard()
        snap = self.watcher.current
        tool, args, payload = copy_command(snap)
        if not (os.environ.get("WAYLAND_DISPLAY") and tool and snap is not None and cb.ownsClipboard()):
            return
        md = cb.mimeData(QClipboard.Mode.Clipboard)
        if md is None or md.hasFormat("x-kaomi") or md.hasFormat(SECRET_HINT):
            return                               # a lent emoji: not worth keeping
        proc = QProcess(self)
        proc.start(tool, args)
        proc.write(QByteArray(payload)); proc.closeWriteChannel()
        proc.waitForFinished(500)                # exits once the clipboard is handed over
        log("clipboard: handed over to " + os.path.basename(tool) + " before quitting")

    # ---- deleting from clipboard history also updates the real clipboard (like Windows)
    def _is_on_clipboard(self, it):
        cur = self.watcher.current
        if cur is None:
            return False
        if snap_hash(cur) == it.hash or any(hashlib.sha1(d).hexdigest() == it.hash for _, d in cur.extra):
            return True
        return it.kind == "text" and cur.mime.startswith("text/plain") \
            and cur.data.decode("utf-8", errors="replace") == it.payload

    # Plasma keeps its own clipboard history (Klipper) next to this one, saved on
    # disk. Deleting here alone left the item in there, and with "Prevent empty
    # clipboard" Klipper even put it straight back on the clipboard. So a delete
    # or Clear all now also asks Klipper to wipe its history: one D-Bus call that
    # empties Klipper's list and the clipboard (and middle-click selection) in one go.
    def _wipe_everywhere(self, then=None):
        """Ask Klipper to forget everything and empty the clipboard. Falls back to
        wl-copy --clear when Klipper isn't around. `then` runs once it is done."""
        self.watcher.forget()
        self.clip.cancel()
        self._wl_drop_queued()
        epoch = self.watcher.epoch

        def after():
            # only if nothing else happened meanwhile (another delete / Clear all /
            # a copy / an emoji pick): then the clipboard is still the empty one we made
            if then and self.watcher.epoch == epoch and self.watcher.current is None:
                then()

        def fallback():
            cb = QGuiApplication.clipboard()
            tool = kaomi_copy() or wlc("wl-copy")
            if self.clip._can_set_directly():
                cb.clear(QClipboard.Mode.Clipboard)
                if cb.supportsSelection():
                    cb.clear(QClipboard.Mode.Selection)
                log("clipboard: emptied (Klipper not reachable)")
                after()
            elif tool and os.environ.get("WAYLAND_DISPLAY"):
                t2, a2, _ = copy_command(None, primary=True)
                QProcess.startDetached(t2, a2)
                t1, a1, _ = copy_command(None)
                proc = QProcess(self)
                proc.finished.connect(lambda *_: (proc.deleteLater(), after()))
                proc.start(t1, a1); proc.closeWriteChannel()   # `after` once it has really cleared
                log("clipboard: emptied with wl-copy (Klipper not reachable)")
            else:
                after()

        def ok():
            log("clipboard: Klipper wiped its history and emptied the clipboard")
            after()

        def err(message):
            log("clipboard: Klipper didn't answer (" + message + ")")
            fallback()
        try:
            from PyQt6.QtDBus import QDBusConnection, QDBusMessage
            msg = QDBusMessage.createMethodCall("org.kde.klipper", "/klipper",
                                                "org.kde.klipper.klipper", "clearClipboardHistory")
            reply = DBusReply(self, ok, err)
            # asynchronous: Klipper may be busy reading a clipboard the picker owns
            sent = QDBusConnection.sessionBus().callWithCallback(msg, reply.ok, reply.err, 2000)
        except Exception as ex:
            log(f"clipboard: D-Bus unavailable ({ex})")
            sent = False
        if not sent:
            fallback()

    def delete_clip_item(self, it):
        """Remove an item for good: from this list, from Plasma's own history, and
        from the clipboard if it is what's there right now (which then stays empty).
        Any other item that was on the clipboard is put back afterwards."""
        was_current = self._is_on_clipboard(it)
        keep = None if was_current else self.watcher.current
        self.store.delete(it)
        self._wipe_everywhere(then=(lambda: self.write_clipboard(keep)) if keep is not None else None)
        log(f"clipboard: deleted an item (was on clipboard: {was_current})")

    def clear_clip_history(self):
        """Clear all: this list, Plasma's history and the clipboard are all emptied.
        (Pinned items stay pinned.) Anything you copy after this shows up normally."""
        self.store.clear()
        self._wipe_everywhere()
        log("clipboard: cleared history")

    def can_type(self):
        # api 7: the plugin commits text the way an input method does (the only way
        # Chrome takes emoji) and waits for focus itself. Older plugins: paste.
        # (needs no KDE input permission: the plugin types, nothing is pasted)
        return self.conf["paste_keys"] != "none" and bool(self.conf.get("type_emoji")) \
            and self.kplug.api >= 7 and self.kplug.can_commit

    def _stage(self, text):
        """Get `text` ready to go in. Returns it if the KWin plugin will type it
        (pass that on to _send_paste); otherwise it is lent through the
        clipboard and this returns None."""
        if self.can_type():
            return text
        self.clip.lend(text)
        return None

    def can_paste(self):
        return self.paster.ui is not None and self.conf["paste_keys"] != "none"

    def after_copy_only(self, via, msg):
        c = self.conf
        if c["close_on_" + via]:
            self.hide()
        else:
            self.info.setText(msg)

    def insert(self, via, typed=None):
        """Put the staged pick into the app you were in. `typed`: what _stage
        returned (text the plugin types), None when it is on the clipboard."""
        c = self.conf
        close = c["close_on_" + via]
        delay = int(c["paste_delay_ms"])
        if close:
            self.hide()
            QTimer.singleShot(delay, lambda: self._send_paste(c["paste_keys"], None, typed))
            return
        self.busy = True
        if self.kwin_ok:
            self.signal_kwin("back")                       # ask KWin to focus the previous app
            QTimer.singleShot(delay, lambda: self._paste_if_away(c, typed))
        else:
            self._hide_paste_return(c, typed)

    def _paste_if_away(self, c, typed=None):
        if self.isActiveWindow():
            # KWin didn't move focus away: never paste into our own search box
            log("focus stayed on the picker; using hide/paste/return instead")
            self._hide_paste_return(c, typed)
            return
        def after():
            QTimer.singleShot(90, lambda: self.signal_kwin("front"))   # focus the picker again
            QTimer.singleShot(260, self._done_busy)
        self._send_paste(c["paste_keys"], after, typed)

    def _hide_paste_return(self, c, typed=None):
        """Hide briefly so focus returns to the app, paste, then come back."""
        delay = int(c["paste_delay_ms"])
        self._own_hide = True
        self.hide()
        self.busy = True

        def after():
            QTimer.singleShot(120, self._return_after_paste)
            QTimer.singleShot(400, self._done_busy)
        QTimer.singleShot(delay, lambda: self._send_paste(c["paste_keys"], after, typed))

    def _return_after_paste(self):
        if self._own_hide:                       # unless you opened it again yourself meanwhile
            self._own_hide = False
            self.present(keep_state=True)

    def _send_paste(self, keys, after=None, typed=None):
        """Put the pick into the focused app: the plugin types `typed` (see
        _stage), or else the keys paste what was lent to the clipboard. `after()`
        runs once, when it is in the app's hands (typing: when the plugin says so)."""
        after = after or (lambda: None)
        if typed is not None:
            def paste_instead():                 # the plugin said it can't type this one
                if not self.can_paste():
                    log("insert: couldn't type it, and pasting needs KDE's input permission")
                    after()
                    return
                if self.isActiveWindow():
                    log("insert: couldn't type it; the panel has focus, so not pasting")
                    after()
                    return
                self.clip.lend(typed)

                def paste():
                    if not self.isActiveWindow():    # never into the panel's search box
                        self.clip.about_to_paste()
                        self.paster.paste(keys)
                    after()
                QTimer.singleShot(int(self.conf["paste_delay_ms"]), paste)
            self.kplug.type_text(typed, paste_instead, after)
            return
        self.clip.about_to_paste()
        self.paster.paste(keys)
        after()

    def _done_busy(self):
        if self.cycling:
            return                    # a paste batch is still running; it clears busy itself
        self.busy = False
        self._focus_current()

    def signal_kwin(self, what):
        self.title_n += 1
        self.setWindowTitle(f"{self.title_base()} [{what}:{self.title_n}]")

    def title_base(self):
        t = f"Kaomi {{place:{self.conf['placement']}}}"
        spot = self._spot
        if self.conf["placement"] == "caret" and spot:
            t += "{spot:%d,%d,%d}" % (spot[0], spot[1], spot[3])
        if self.conf["placement"] == "caret" and self.caret and self.caret.by_pid:
            t += "{caret:" + ";".join("%d,%d,%d,%d" % (pid, *v) for pid, v in self.caret.by_pid.items()) + "}"
        return t

    # ---- show / hide
    def toggle(self, mode="emoji", token=""):
        self._own_hide = False
        if self.isVisible():
            same = (mode == "clipboard") == (self.mode == "clipboard")   # emoji/kaomoji/symbols: one family
            if same and not self.in_settings():
                self.hide()
            else:
                if self.in_settings():
                    self.header.set_settings_mode(False)
                self.set_mode(mode)
                self._leave_passive()
            return
        self.conf = load_conf()
        self.mode = mode
        self.present(token=token)

    def present(self, token="", keep_state=False):
        if not keep_state:
            if self.in_settings():
                self.header.set_settings_mode(False)
            self.search.blockSignals(True); self.search.clear(); self.search.blockSignals(False)
            self.refresh()
            self.set_mode(self.mode)
        if token:
            os.environ["XDG_ACTIVATION_TOKEN"] = token
        self.was_active = False
        self.shown_at = time.monotonic()
        if self.kplug.active:
            self.kplug._tell_pid()
        # ask KWin where the text cursor is *before* the panel takes focus
        if not keep_state:
            self._spot = self.kplug.cursor() if self.conf["placement"] == "caret" else None
        self.setWindowTitle(self.title_base())
        log(f"open: placement={self.conf['placement']} kwin_text_cursor={self._spot or 'none'} "
            f"atspi={self.caret.by_pid if self.caret and self.caret.by_pid else 'off/none'}")
        self.show(); self.raise_(); self.activateWindow()
        self._focus_current()
        if self.kwin_ok:
            QTimer.singleShot(40, lambda: self.signal_kwin("front"))

    def hideEvent(self, ev):
        self.was_active = False
        if self.passive:
            self.kplug.set_passive(False)
        self.passive = self.p_front_after = False
        self._click_target = None
        if not self._own_hide:
            self.pending_text = ""               # you closed it: forget picks not pasted yet
            self.p_jobs = []
        super().hideEvent(ev)

    def event(self, ev):
        if ev.type() == QEvent.Type.WindowActivate:
            self.was_active = True
        elif ev.type() == QEvent.Type.WindowDeactivate:
            # close when you click elsewhere, like Windows (not during our own paste or menus)
            # (in passive mode losing focus is the point; KWin reports clicks and app switches)
            if self.was_active and not self.busy and not self.passive and not QApplication.activePopupWidget():
                QTimer.singleShot(80, self._maybe_hide)
        return super().event(ev)

    def _maybe_hide(self):
        if not self.busy and not self.passive and not self.isActiveWindow() \
                and not QApplication.activePopupWidget():
            self.hide()

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key.Key_Escape:
            self.escape_action()
            return
        super().keyPressEvent(ev)

    def eventFilter(self, obj, ev):
        if obj is self.search and ev.type() == QEvent.Type.MouseButtonPress and self.passive:
            self._leave_passive()                # clicked the search box: you want to type here
        if obj is self.search and ev.type() == QEvent.Type.KeyPress:
            k = ev.key()
            arrows = (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Left, Qt.Key.Key_Right)
            if k in arrows and ev.modifiers() in (Qt.KeyboardModifier.NoModifier,
                                                  Qt.KeyboardModifier.KeypadModifier):
                self.grid.move_sel(k); return True
            if k in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if 0 <= self.grid.sel < len(self.grid.pos):
                    self.pick(self.grid.pos[self.grid.sel][1], via="keyboard")
                return True
            if k == Qt.Key.Key_Escape:
                self.escape_action()
                return True
            if k == Qt.Key.Key_Delete and not self.search.text() and self.grid.sel >= 0:
                self.remove_recent(self.grid.sel)    # only acts on a recent emoji
                return True
            if k in (Qt.Key.Key_PageDown, Qt.Key.Key_PageUp):
                sb = self.scroll.verticalScrollBar()
                sb.setValue(sb.value() + (1 if k == Qt.Key.Key_PageDown else -1) * sb.pageStep())
                top = sb.value()
                first = next((i for i, (r, _) in enumerate(self.grid.pos) if r.top() >= top), None)
                if k == Qt.Key.Key_PageDown and sb.value() >= sb.maximum() and self.grid.pos:
                    first = len(self.grid.pos) - 1           # at the bottom: the very last emoji
                if first is not None:                    # select the first emoji now in view
                    self.grid.sel = first
                    self.show_info(self.grid.pos[first][1]); self.grid.update()
                return True
        return super().eventFilter(obj, ev)

    def paintEvent(self, ev):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath(); path.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)
        p.fillPath(path, self.theme.bg)
        p.setPen(QPen(self.theme.border, 1)); p.drawPath(path)


def main():
    # only one picker at a time (e.g. autostart and an early Meta+. racing).
    # Taken before anything else, so a losing copy touches nothing.
    import fcntl
    global _LOCK
    _LOCK = open(os.path.join(RUNTIME, APP_ID + ".lock"), "w")
    try:
        fcntl.flock(_LOCK, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        for _ in range(30):                    # the other one is starting: hand over to it
            if try_client():
                sys.exit(0)
            time.sleep(0.1)
        sys.exit(0)
    try:
        rotate_log()
        sys.stderr = _open_log()
        import faulthandler; faulthandler.enable(sys.stderr)
    except Exception:
        pass
    log(f"starting (pid {os.getpid()}, wayland={bool(os.environ.get('WAYLAND_DISPLAY'))})")
    import signal
    signal.signal(signal.SIGINT, signal.SIG_DFL)   # let Ctrl+C stop it in a terminal
    app = QApplication(sys.argv)
    app.setApplicationName(APP_ID)
    app.setDesktopFileName(APP_ID)
    app.setQuitOnLastWindowClosed(False)
    kwin_ok = load_kwin_helper()
    log(f"kwin helper: {'ok' if kwin_ok else 'NOT running'}")
    picker = Picker(kwin_ok)
    picker.panel_bus = register_panel_bus(picker)

    app.aboutToQuit.connect(picker.hand_over_clipboard)

    QLocalServer.removeServer(SOCK)
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    if not server.listen(SOCK):
        print("could not listen on", SOCK, server.errorString(), file=sys.stderr)

    def on_conn():
        c = server.nextPendingConnection()
        def read():
            data = bytes(c.readAll()).decode(errors="ignore").strip()
            if data.startswith("quit"):
                c.disconnectFromServer()
                QTimer.singleShot(0, app.quit)
                return
            if data.startswith("kplug-check"):
                picker.kplug.ensure()
            elif data.startswith("toggle"):
                parts = data.split()
                mode = parts[1] if len(parts) > 1 and parts[1] in ("emoji", "clipboard") else "emoji"
                picker.toggle(mode, parts[2] if len(parts) > 2 else "")
            c.disconnectFromServer()
        c.readyRead.connect(read)
        c.disconnected.connect(c.deleteLater)
    server.newConnection.connect(on_conn)

    if not DAEMON:
        QTimer.singleShot(0, lambda: picker.toggle(MODE, os.environ.pop("XDG_ACTIVATION_TOKEN", "")))
    sys.exit(app.exec())


# ------------------------------------------------------------- emoji data --
# DATA below is the emoji list: groups, emoji, names and search keywords,
# compressed. It comes from:
#   - Unicode's emoji data (groups, names, order), via unicode-emoji-json
#     by Mu-An Chiou: https://github.com/muan/unicode-emoji-json
#   - emojilib by Mu-An Chiou (search keywords): https://github.com/muan/emojilib
# Their notices:
#
# unicode-emoji-json: The MIT License (MIT)
# Copyright (c) 2019 Mu-An Chiou
#
# emojilib: The MIT License (MIT)
# Copyright (c) 2014 Mu-An Chiou
#
# (same terms for both:)
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# Unicode emoji data: UNICODE LICENSE V3
#
# COPYRIGHT AND PERMISSION NOTICE
#
# Copyright © 1991-2023 Unicode, Inc.
#
# NOTICE TO USER: Carefully read the following legal agreement. BY
# DOWNLOADING, INSTALLING, COPYING OR OTHERWISE USING DATA FILES, AND/OR
# SOFTWARE, YOU UNEQUIVOCALLY ACCEPT, AND AGREE TO BE BOUND BY, ALL OF THE
# TERMS AND CONDITIONS OF THIS AGREEMENT. IF YOU DO NOT AGREE, DO NOT
# DOWNLOAD, INSTALL, COPY, DISTRIBUTE OR USE THE DATA FILES OR SOFTWARE.
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of data files and any associated documentation (the "Data Files") or
# software and any associated documentation (the "Software") to deal in the
# Data Files or Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, and/or sell
# copies of the Data Files or Software, and to permit persons to whom the
# Data Files or Software are furnished to do so, provided that either (a)
# this copyright and permission notice appear with all copies of the Data
# Files or Software, or (b) this copyright and permission notice appear in
# associated Documentation.
#
# THE DATA FILES AND SOFTWARE ARE PROVIDED "AS IS", WITHOUT WARRANTY OF ANY
# KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT OF
# THIRD PARTY RIGHTS.
#
# IN NO EVENT SHALL THE COPYRIGHT HOLDER OR HOLDERS INCLUDED IN THIS NOTICE
# BE LIABLE FOR ANY CLAIM, OR ANY SPECIAL INDIRECT OR CONSEQUENTIAL DAMAGES,
# OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS,
# WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION,
# ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THE DATA
# FILES OR SOFTWARE.
#
# Except as contained in this notice, the name of a copyright holder shall
# not be used in advertising or otherwise to promote the sale, use or other
# dealings in these Data Files or Software without prior written
# authorization of the copyright holder.
DATA = "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"

if __name__ == "__main__":
    main()
