from ambassador.ports.evaluator import (
    AnswerDecision,
    AssessmentProposal,
    FaceoffContext,
    ObjectionBatch,
    ObjectionProposal,
)


class FakeEvaluator:
    """Scripted integration demo, not AI persuasion: +5, +30, -30."""

    async def generate(self, context: FaceoffContext) -> ObjectionBatch:
        number = len(context.game.history)
        topic_examples = dict(context.game.scenario.objections_by_persona)
        return ObjectionBatch(
            objections=[
                ObjectionProposal(
                    persona_id=p.id,
                    concern_id=context.concern.id if context.concern else None,
                    text_tr=context.concern.example_tr
                    if context.concern
                    else topic_examples.get(p.id, p.objection_examples_tr)[
                        number % len(topic_examples.get(p.id, p.objection_examples_tr))
                    ],
                )
                for p in context.selected_personas
            ]
        )

    async def evaluate(self, context: FaceoffContext) -> AnswerDecision:
        score = (5, 30, -30)[len(context.game.history) % 3]
        return AnswerDecision(
            assessments=[
                AssessmentProposal(objection_id=o.id, score=score)
                for o in context.game.current_objections
            ],
            feedback_tr={
                30: "Bu çözüm günlük işleri kolaylaştıracak, halk reforma ısındı!",
                5: "Öneriniz bir başlangıç, halk nasıl uygulanacağını merak ediyor!",
                -30: "Bu cevap sorunu çözmek yerine görmezden geliyor!",
            }[score],
        )
