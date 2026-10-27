{{/*
Expand the name of the chart.
*/}}
{{- define "smtp-oauth-relay.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name, truncated to 63 chars (DNS naming limit).
*/}}
{{- define "smtp-oauth-relay.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{- define "smtp-oauth-relay.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "smtp-oauth-relay.labels" -}}
helm.sh/chart: {{ include "smtp-oauth-relay.chart" . }}
{{ include "smtp-oauth-relay.selectorLabels" . }}
app.kubernetes.io/version: {{ include "smtp-oauth-relay.imageTag" . | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "smtp-oauth-relay.selectorLabels" -}}
app.kubernetes.io/name: {{ include "smtp-oauth-relay.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "smtp-oauth-relay.imageTag" -}}
{{- .Values.image.tag | default .Chart.AppVersion }}
{{- end }}

{{- define "smtp-oauth-relay.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "smtp-oauth-relay.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Name of the secret holding the TLS certificate and key (TLS_SOURCE=file).
*/}}
{{- define "smtp-oauth-relay.tlsSecretName" -}}
{{- if .Values.tls.certManager.enabled }}
{{- default (printf "%s-tls" (include "smtp-oauth-relay.fullname" .)) .Values.tls.certManager.secretName }}
{{- else }}
{{- .Values.tls.existingSecret.name }}
{{- end }}
{{- end }}

{{- define "smtp-oauth-relay.tlsCertKey" -}}
{{- if .Values.tls.certManager.enabled }}tls.crt{{ else }}{{ .Values.tls.existingSecret.certKey }}{{ end }}
{{- end }}

{{- define "smtp-oauth-relay.tlsKeyKey" -}}
{{- if .Values.tls.certManager.enabled }}tls.key{{ else }}{{ .Values.tls.existingSecret.keyKey }}{{ end }}
{{- end }}

{{/*
Validate value combinations that the schema cannot express.
*/}}
{{- define "smtp-oauth-relay.validate" -}}
{{- $tls := .Values.tls }}
{{- if eq $tls.source "file" }}
{{- if and $tls.certManager.enabled $tls.existingSecret.name }}
{{- fail "tls.certManager.enabled and tls.existingSecret.name are mutually exclusive" }}
{{- end }}
{{- if not (or $tls.certManager.enabled $tls.existingSecret.name) }}
{{- fail "tls.source=file requires tls.certManager.enabled=true or tls.existingSecret.name" }}
{{- end }}
{{- if $tls.certManager.enabled }}
{{- if not $tls.certManager.issuerRef.name }}
{{- fail "tls.certManager.issuerRef.name is required when tls.certManager.enabled=true" }}
{{- end }}
{{- if not $tls.certManager.dnsNames }}
{{- fail "tls.certManager.dnsNames must contain at least one DNS name" }}
{{- end }}
{{- end }}
{{- else if eq $tls.source "keyvault" }}
{{- if or (not .Values.azure.keyVault.url) (not .Values.azure.keyVault.certName) }}
{{- fail "tls.source=keyvault requires azure.keyVault.url and azure.keyVault.certName" }}
{{- end }}
{{- end }}
{{- if and (ne $tls.source "file") (or $tls.certManager.enabled $tls.existingSecret.name) }}
{{- fail "tls.certManager and tls.existingSecret are only used with tls.source=file" }}
{{- end }}
{{- if and .Values.azure.tables.forceUsage (not .Values.azure.tables.url) }}
{{- fail "azure.tables.forceUsage requires azure.tables.url" }}
{{- end }}
{{- if and .Values.azureWorkloadIdentity.enabled (not .Values.azureWorkloadIdentity.clientId) }}
{{- fail "azureWorkloadIdentity.clientId is required when azureWorkloadIdentity.enabled=true" }}
{{- end }}
{{- end }}
