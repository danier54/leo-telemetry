{{- define "demux.labels" -}}
app.kubernetes.io/name: demux
app.kubernetes.io/part-of: leo-telemetry
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}