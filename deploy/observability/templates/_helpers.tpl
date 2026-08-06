{{- define "observability.labels" -}}
app.kubernetes.io/name: observability
app.kubernetes.io/part-of: leo-telemetry
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}
