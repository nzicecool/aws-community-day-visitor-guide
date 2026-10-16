# Agent Manager / OpenChoreo deployment

These files are safe to commit. They contain runtime configuration and secret **references only**; no credential is stored in the repository.

## Managed Gemini binding

In Agent Manager, create a model configuration for the Default environment using the available managed Gemini provider. Map its generated values to:

- `LLM_PROVIDER_URL` ← provider URL
- `LLM_PROVIDER_KEY` ← provider API key

The application uses Gemini-native `generateContent` requests. Deploy the component with the values in `component-runtime-environment-variables.json` and automatic OpenTelemetry instrumentation enabled.

## OpenChoreo secret reference

`llm-runtime-secret-reference.yaml` documents an equivalent OpenChoreo reference for a secret managed outside source control. If this approach is used, the secret must exist at:

```text
secret/default/generic/aws-community-day-visitor-guide-llm-provider
```

with property `api_key`.

The service never logs or returns `LLM_PROVIDER_KEY`. Its `/health` endpoint exposes only non-sensitive model and schedule metadata.
