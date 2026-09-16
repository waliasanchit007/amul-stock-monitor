# Amul Stock Monitor

A small, local macOS monitor for Amul High Protein **Rose Lassi** and **Plain Lassi**, 200 mL packs of 30. It checks delivery availability for your PIN code and sends restock alerts through Mac notifications or an optional Slack workflow.

No AI model, Codex subscription, open browser, Amul login, or automatic purchasing is involved. Nothing starts merely by cloning the repository.

## How it works

1. Create a fresh anonymous Amul storefront session.
2. Resolve the delivery PIN and verify the selected regional store.
3. Fetch each exact product and check its identity and explicit availability flag.
4. Notify once when a product becomes available, and again only after a later confirmed restock.

A positive inventory quantity or “Add to Cart” text alone does **not** establish availability. Errors stay separate from out-of-stock results. Three consecutive check failures produce a local warning.

## Requirements

- macOS, Python 3.10 or newer, and the built-in `curl` and `launchd` tools.
- `terminal-notifier` for local notifications. Install with `brew install terminal-notifier`, and allow its notifications in System Settings.
- An internet connection. The Mac must be awake and logged into your account.

There are no third-party Python dependencies.

## Set up and run

```sh
git clone https://github.com/waliasanchit007/amul-stock-monitor.git
cd amul-stock-monitor
export AMUL_PINCODE=110001  # replace with your delivery PIN
python3 monitor.py --once
python3 manage.py install
```

`install` runs a check immediately, starts checks every 15 minutes, and enables them at login. It saves the selected PIN, data directory and executable paths into your local LaunchAgent, so it does not depend on an interactive shell. Repeat `install` after changing your PIN or moving/upgrading the Python installation. Keep this checkout in place while its schedule is installed.

If you want a different state directory, set `AMUL_DATA_DIR` to an **absolute path** before installing. The default is `~/Library/Application Support/AmulStockMonitor`.

```sh
python3 manage.py status   # schedule and last saved result
python3 manage.py pause    # disable future runs and unload the job
python3 manage.py resume   # use the installed schedule again
python3 manage.py check    # immediate check using this shell's configuration
```

Checks pause while the Mac sleeps. The program does not keep it awake. A one-off check can send an alert if the product is available. Set `AMUL_PINCODE` in each new shell when running one-off checks; otherwise the example PIN `110001` is used.

## Optional Slack DMs

Use Slack's built-in Workflow Builder if your workspace permits webhook workflows. Slack plan and workspace permissions apply; this project does not bypass them or purchase anything.

1. Create a workflow with **From a webhook** as its trigger.
2. Define one **Text** variable named `message`.
3. Add **Send a message to a person**, choose the recipient, and insert the `message` variable as its entire message body.
4. Set finding/using and copying permissions to **Workflow managers only** if you want a private workflow. Review its manager list.
5. Publish it and copy the generated webhook URL.
6. Copy `slack-webhook.example.json` into your data directory as `slack-webhook.json`. Set `enabled` to `true`, insert your URL, and restrict the file to your account with `chmod 600`.

Keep the webhook URL secret. It can trigger messages to the workflow's selected recipient. Do not put it in this repository, shell history, issue reports or logs.

With Slack enabled, **only restock alerts** go to Slack; error/recovery and setup notifications stay on the Mac. Without Slack configuration, restocks use Mac notifications. Requests use standard HTTPS and do not call an AI service. Slack's acceptance of a webhook is not proof of DM delivery—check the workflow's Activity Log when verifying your setup.

## Stop everything

Run `python3 manage.py pause`. If you enabled Slack, also set `enabled` to `false` in its local configuration and unpublish the workflow in Slack. To uninstall the schedule after pausing, remove `~/Library/LaunchAgents/local.amul-stock-monitor.plist`. State and logs can be retained separately.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

Tests use synthetic availability responses and mocked outbound delivery; they do not contact Amul or send Slack messages. They cover identity/schema validation, regional store selection, deduplication, failure recovery, notification retry, Slack response validation and configuration persistence across scheduled runs.

## Limitations

- Amul's storefront interface is unofficial and may change.
- Polling can miss short restocks. A successful check does not reserve stock.
- Ambiguous delivery timeouts may cause duplicate messages on retry; exactly-once delivery is not guaranteed.
- Notification settings and Focus mode can suppress Mac banners.
- This project has been exercised on macOS; other operating systems are not supported by its scheduler/notifier integration.
- Local runtime state and credentials are intentionally excluded. A clone is not preconfigured for any recipient or workspace.

## Source notes

The client follows Amul's public storefront request and regional-session behavior. Session conventions were cross-checked against the [Amul Notify client](https://github.com/SwapnilSoni1999/amul-notify/blob/main/src/libs/amulApi.lib.ts); this utility does not install that bot or its ordering features.

See [Slack's webhook workflow guide](https://slack.com/help/articles/360041352714-Build-a-workflow--Create-a-workflow-that-starts-outside-of-Slack) for workflow requirements and [terminal-notifier](https://github.com/julienXX/terminal-notifier) for notification support.
