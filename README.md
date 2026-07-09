# AxiomOS Runtime 1.1 Dev

Post-1.0 development build focused on Hermes-style setup and config UX.

## New commands

```bash
axiom setup --dry-run
axiom setup provider cloudflare cf_p26 --account-env CLOUDFLARE_ACCOUNT_ID_P26 --token-env CLOUDFLARE_API_TOKEN_P26
axiom setup memory --attention-limit 7
axiom setup permissions --profile dev

axiom config init
axiom config path
axiom config list
axiom config get provider.default
axiom config set provider.default cf_p26
```

## Home layout

```text
~/.axiom/
  config.yaml
  .env
  identity/
  memory/
  packages/
  receipts/
  skills/
  cron/
```

Secrets go to `.env`. Non-secret settings go to `config.yaml`.


## Self-description

```bash
axiom about
axiom about status
axiom about roadmap
axiom about architecture
axiom about constitution
axiom about hermes
```
