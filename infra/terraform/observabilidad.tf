# ---------------------------------------------------------------------------
# FIL_16 — Observabilidad mínima: alerta de fallos de Glue -> SNS -> email.
#
# Motivación: los incidentes FIL_09 (37/48 jobs de Glue en LAUNCH ERROR
# durante 28 h) y FIL_11 (Gold escribiendo 0 filas) se encontraron por QA
# manual, sin ninguna alarma. Esto cubre la mitad "el job falló" con coste
# ~0. La mitad "el job dice SUCCEEDED pero no escribe datos" la cubre el
# chequeo de frescura `herramientas/salud/frescura_gold.py` (se corre a
# mano / por cron, no necesita infra).
#
# Estado: DISEÑADO, sin `terraform apply` todavía -- mismo patrón que
# `glue_scheduling.tf` (tarea 064). Razones:
#   - El pipeline está congelado (`pipeline_enabled = false`, ver
#     `variables.tf`): ningún job corre, así que la regla no dispararía.
#   - `aws_sns_topic_subscription` por email exige confirmación manual desde
#     el buzón (`var.alertas_email`), un paso humano que no se puede
#     automatizar en el `apply`.
# Cuando se reanude la ingesta: rellenar `alertas_email` en el `.tfvars`
# local, `terraform apply -target=aws_sns_topic.alertas_pipeline -target=...`
# y confirmar la suscripción. Coste: SNS cobra 0 por los primeros 1000
# emails/mes; EventBridge no cobra por reglas sobre eventos de AWS.
# ---------------------------------------------------------------------------

resource "aws_sns_topic" "alertas_pipeline" {
  name = "${var.project_name}-${var.environment}-alertas-pipeline"
}

# Permite que EventBridge publique en el topic.
data "aws_iam_policy_document" "alertas_pipeline_topic" {
  statement {
    sid       = "AllowEventBridgePublish"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.alertas_pipeline.arn]

    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }

    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [aws_cloudwatch_event_rule.glue_job_failed.arn]
    }
  }
}

resource "aws_sns_topic_policy" "alertas_pipeline" {
  arn    = aws_sns_topic.alertas_pipeline.arn
  policy = data.aws_iam_policy_document.alertas_pipeline_topic.json
}

# Suscripción email opcional: sólo si se ha configurado la dirección.
resource "aws_sns_topic_subscription" "alertas_email" {
  count = var.alertas_email == "" ? 0 : 1

  topic_arn = aws_sns_topic.alertas_pipeline.arn
  protocol  = "email"
  endpoint  = var.alertas_email
}

# Regla EventBridge: cualquier job run de Glue que acabe mal.
resource "aws_cloudwatch_event_rule" "glue_job_failed" {
  name        = "${var.project_name}-${var.environment}-glue-job-failed"
  description = "Job de Glue en estado FAILED/TIMEOUT/ERROR -> SNS (FIL_16)"

  event_pattern = jsonencode({
    source      = ["aws.glue"]
    detail-type = ["Glue Job State Change"]
    detail = {
      state = ["FAILED", "TIMEOUT", "ERROR"]
    }
  })
}

resource "aws_cloudwatch_event_target" "glue_job_failed_sns" {
  rule      = aws_cloudwatch_event_rule.glue_job_failed.name
  target_id = "alertas-pipeline-sns"
  arn       = aws_sns_topic.alertas_pipeline.arn

  # Mensaje legible en el email en vez del evento crudo.
  input_transformer {
    input_paths = {
      job   = "$.detail.jobName"
      state = "$.detail.state"
      run   = "$.detail.jobRunId"
      msg   = "$.detail.message"
      time  = "$.time"
    }
    input_template = <<-EOT
      "Glue <job> terminó en <state> (run <run>) a las <time>. Motivo: <msg>"
    EOT
  }
}
