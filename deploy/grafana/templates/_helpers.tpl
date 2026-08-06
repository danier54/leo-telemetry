{{- define "grafana.labels" -}}
app.kubernetes.io/name: grafana
app.kubernetes.io/part-of: leo-telemetry
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}
