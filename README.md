# Dock Display

A [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) plugin that lets you keep the picture on the Steam Deck screen while it sits in a dock with a monitor attached — so the dock can be used just as a charger, without unplugging the cable.

[Русская версия ниже](#русский) · Mirror: [GitFlic](https://gitflic.ru/project/kernine/dock-display)

## Features

- **Use external display** toggle: off keeps the picture on the Deck screen even when a monitor is connected; on restores the normal SteamOS behaviour.
- **Confirm switching** (on by default): after switching to the monitor a dialog asks you to keep it. If you don't confirm within 15 seconds — for example because the monitor is off and you see nothing — the picture returns to the Deck screen.
- No flicker on the Deck screen while the monitor wakes up and re-negotiates the link.
- The choice survives reboots, sleep and re-plugging the cable.
- When the plugin is disabled or uninstalled, the monitor always goes back to normal behaviour.

## Installation

The plugin is not in the Decky plugin store, so it is installed from a ZIP file:

1. In Game Mode open Quick Access (`…`) → Decky → ⚙️ Settings → **General** and enable **Developer mode**.
2. Open the new **Developer** section and choose **Install Plugin from URL**.
3. Paste the link to `dock-display.zip` from the [latest release](https://github.com/Kernien/dock-display/releases/latest) and confirm.

Alternatively download the ZIP to the Deck and use **Install Plugin from ZIP File**.

To update, install the newer release the same way.

## How it works

In Game Mode the picture is driven by gamescope, which always prefers an external output when one is connected.
The plugin (backend runs as root) writes `off` to the external connector's `/sys/class/drm/card*-*/status`, which makes the kernel report it as disconnected, and asks gamescope to re-scan outputs with `gamescopectl backend_set_dirty`.
Switching back writes `detect`.
While switching to the monitor the Deck screen is kept asleep (`drm_sleep_internal_screen`) until the link stays up for a few seconds, because many monitors and docks drop hotplug once or twice when they wake up.

Tested on Steam Deck LCD with SteamOS 3.8 and Decky Loader 3.2.

## Development

```bash
pnpm install
pnpm build
```

The plugin consists of `dist/index.js`, `main.py`, `plugin.json`, `package.json` and `LICENSE`.
Releases are built by GitHub Actions when a `v*` tag is pushed.

This plugin was developed with the help of an AI coding assistant (Claude).

## License

BSD-3-Clause, based on the [Decky plugin template](https://github.com/SteamDeckHomebrew/decky-plugin-template).

---

## Русский

Плагин для [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader), который позволяет оставить изображение на экране Steam Deck, когда он стоит в доке с подключённым монитором. Док можно использовать просто как зарядку, не вынимая кабель.

### Возможности

- Переключатель **«Выводить на внешний монитор»**: выключен — изображение остаётся на Steam Deck даже при подключённом мониторе; включён — обычное поведение SteamOS.
- **«Подтверждать переключение»** (включено по умолчанию): после переключения на монитор появляется окно подтверждения. Если не подтвердить за 15 секунд (например, монитор выключен и ничего не видно), изображение вернётся на Steam Deck.
- Экран Steam Deck не мигает, пока монитор просыпается и переподключается.
- Выбор сохраняется после перезагрузки, сна и переподключения кабеля.
- Если плагин отключить или удалить, монитор всегда возвращается к обычному поведению.

### Установка

Плагина нет в магазине Decky, он устанавливается из ZIP:

1. В игровом режиме откройте меню быстрого доступа (`…`) → Decky → ⚙️ Настройки → **General** и включите **Developer mode**.
2. В появившемся разделе **Developer** выберите **Install Plugin from URL**.
3. Вставьте ссылку на `dock-display.zip` из [последнего релиза](https://github.com/Kernien/dock-display/releases/latest) и подтвердите.

Либо скачайте ZIP на Deck и выберите **Install Plugin from ZIP File**.

Обновление — так же, из нового релиза.
