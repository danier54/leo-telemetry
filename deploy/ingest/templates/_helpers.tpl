{{- define "ingest.labels" -}}
app.kubernetes.io/name: ingest
app.kubernetes.io/part-of: leo-telemetry
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}
