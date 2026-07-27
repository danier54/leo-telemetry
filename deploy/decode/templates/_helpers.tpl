{{- define "decode.labels" -}}
app.kubernetes.io/name: decode
app.kubernetes.io/part-of: leo-telemetry
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}
