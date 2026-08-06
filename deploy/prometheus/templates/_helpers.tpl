{{- define "prometheus.labels" -}}
app.kubernetes.io/name: prometheus
app.kubernetes.io/part-of: leo-telemetry
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}
