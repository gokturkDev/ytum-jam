from ambassador.domain.game import Quality
from ambassador.ports.evaluator import (
    AnswerDecision,
    AssessmentProposal,
    FaceoffContext,
    ObjectionBatch,
    ObjectionProposal,
)


class FakeEvaluator:
    """Scripted integration demo, not AI persuasion: partial, answered, missed."""

    async def generate(self, context: FaceoffContext) -> ObjectionBatch:
        number = len(context.game.history)
        topic_examples = dict(context.game.scenario.objections_by_persona)
        return ObjectionBatch(
            objections=[
                ObjectionProposal(
                    persona_id=p.id,
                    text_tr=topic_examples.get(p.id, p.objection_examples_tr)[
                        number % len(topic_examples.get(p.id, p.objection_examples_tr))
                    ],
                )
                for p in context.selected_personas
            ]
        )

    async def evaluate(self, context: FaceoffContext) -> AnswerDecision:
        quality = (Quality.PARTIAL, Quality.ANSWERED, Quality.MISSED)[len(context.game.history) % 3]
        return AnswerDecision(
            assessments=[
                AssessmentProposal(objection_id=o.id, quality=quality)
                for o in context.game.current_objections
            ],
            feedback_tr={
                Quality.ANSWERED: "Bu çözüm günlük işleri kolaylaştıracak, halk reforma ısındı!",
                Quality.PARTIAL: "Öneriniz bir başlangıç, halk nasıl uygulanacağını merak ediyor!",
                Quality.MISSED: "Bu cevap günlük kaygıya değinmediği için halk henüz ikna olmadı!",
            }[quality],
        )
