import re

from ambassador.domain.game import Persona, Scenario
from ambassador.ports.evaluator import (
    AnswerDecision,
    AssessmentProposal,
    FaceoffContext,
    ObjectionBatch,
    ObjectionProposal,
)
from ambassador.ports.reform_generator import PersonaConcerns, ReformDraft


class FakeEvaluator:
    """Scripted integration demo, not AI persuasion: +5, +30, -30."""

    async def draft_reform(self, topic: str) -> ReformDraft:
        return ReformDraft(
            title_tr=topic[:100],
            decree_tr=f"Kral, {topic[:350]} konusunda halkın yararına yeni bir düzen başlatıyor.",
            public_facts_tr=[
                "Reform, alışılmış düzeni halkın yararına değiştirmeyi amaçlıyor.",
                "Uygulama ayrıntıları halkın kaygıları dinlenerek şekillenecek.",
            ],
            facts_en=[
                "The king is introducing a beneficial reform in a medieval kingdom.",
                "Practical implementation remains open to the people's suggestions.",
            ],
        )

    async def generate_concerns(self, scenario: Scenario, persona: Persona) -> PersonaConcerns:
        title = re.sub(r"[.!?…\r\n]", " ", scenario.title_tr)[:60].strip()
        return PersonaConcerns(
            objections_tr=[
                f"{title} yüzünden günlük işlerim aksarsa geçimimi nasıl sağlayacağım?",
                f"{title} için gereken masrafı ailem nasıl karşılayacak?",
                f"{title} düzenine alışmak için bize kim yardımcı olacak?",
            ]
        )

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
