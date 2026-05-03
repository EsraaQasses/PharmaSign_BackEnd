from django.utils import timezone

from common.choices import PrescriptionAccessTypeChoices
from common.choices import SignStatusChoices
from common.choices import TranscriptionStatusChoices
from transcriptions.exceptions import sanitize_transcription_error
from transcriptions.services import get_gemini_modules

from .models import PrescriptionAccessLog
from .transcription import get_transcription_backend

SIGN_GLOSS_PROMPT_TEMPLATE = """You are an expert Arabic Sign Language interpreter for pharmacy and medical instructions.

Your job is to convert Arabic or Syrian/Levantine medication instructions into a simplified Arabic sign-language style sentence.

Important:
The output should match the style of a Syrian Arabic medical sign-language gloss dataset.
It should NOT be formal Arabic.
It should NOT be a short machine translation.
It should NOT include tashkeel/diacritics.
It should NOT include Markdown, labels, quotes, bullets, or explanations outside the final gloss.

Core style:
- Use simple Syrian/Levantine Arabic words when natural.
- Use direct visual phrases.
- Keep the medical meaning accurate.
- Explain the purpose of the medication when the input mentions it.
- If the disease or condition is complex, explain it simply.
- Prefer words like: الدوا، الهدف، مشان، كيف، لازم، انتبه، ممنوع، مابصير، برا الجسم، الجسم، الدم، اكل، دكتور، مراقبة.
- It is okay to repeat important concepts for clarity, like: زيادة زيادة، شوي شوي، لازم لازم, if useful.
- Use short connected phrases, like a sign-language explanation.
- Remove filler words and complex grammar.
- Preserve dosage, timing, duration, warnings, negation, and route of use.
- Do not invent a disease, dosage, warning, or duration that is not in the input.
- If the input is simple, keep the output simple.
- If the input is complex, expand it into a clear visual explanation.

Normalization rules:
- Remove Arabic diacritics completely.
- Convert Arabic written numbers to digits when useful:
  خمسة -> 5
  سبعة -> 7
  عشرة -> 10
  مرتين -> مرتين or 2 حسب الأسلوب الأنسب
  ثلاث مرات -> تلت مرات or 3 مرات
- Normalize timing:
  بعد الطعام / بعد الأكل -> بعد الاكل
  قبل الطعام / قبل الأكل -> قبل الاكل
  على معدة فاضية / على الريق -> قبل الاكل او معدة فاضية
- Normalize duration:
  لمدة خمسة أيام -> مدة 5 يوم
  لمدة سبعة أيام -> مدة 7 يوم
- Normalize dose:
  حبة وحدة / قرص واحد -> حبة وحدة or حبة 1
  كبسولة وحدة -> كبسولة وحدة
  نقطتين -> نقطة 2
- Keep negation clearly:
  لا، ممنوع، مابصير، بلا

Preferred order:
1. الهدف من الدوا أو المرض إذا موجود
2. كيف الدوا بيساعد أو شو بيعمل
3. طريقة الاستخدام والجرعة
4. التحذيرات والممنوعات
5. متى نراجع الدكتور أو نوقف الدوا إذا موجود

Dataset-style examples:

Original:
هي الحبوب بتساعد على رفع مستوى الصوديوم بالدم. الجرعة بتبلش بحبة وحدة باليوم وبيتم مراقبة مستوى الصوديوم بالدم بشكل دقيق بالمشفى بأول فترة. لازم تحدد كمية السوائل اللي بتشربها باليوم حسب تعليمات الدكتور.
Gloss:
هي حبوب مشان الهدف ملح الدم مرتفع حبة وحدة باليوم ولازم مراقبة ملح الدم ولازم شرب سوائل مختلفة حسب برنامج دكتور تبعو

Original:
هاد الدوا بيعالج مرض ويلسون عن طريق الارتباط بالنحاس الزايد بالجسم وطرحه. الجرعة هي كبسولة وحدة 3 أو 4 مرات باليوم على معدة فاضية. لازم تتبع حمية قليلة النحاس، يعني تتجنب المكسرات والشوكولا والكبدة.
Gloss:
داء ويلسون هو مرض متل بكون في زيادة بالدم النحاس زايد الدوا هو الحل الدوا بياخد النحاس بيتحد معو بينطرح برا الجسم فهمتو لازم الدوا تلاتة او اربعة يوم قبل الاكل لازم الاكل نختارو اكل فيو نحاس طرد يعني بلا الشوكولا بلا الكبدة بلا بلا بلا في نحاس الافضل بلا ما ناكل فهمتو

Original:
هي الحبوب غالية ومتخصصة لعلاج ارتفاع ضغط الشريان الرئوي. الجرعة هي حبة مرتين باليوم. هاد الدوا بيحتاج موافقات خاصة. ممنوع تاخديه إذا كنتي حامل أو عم تخططي للحمل، ولازم تعملي اختبار حمل كل شهر.
Gloss:
دوا هو ضغط الدم مرتفع حل حبتين باليوم ننتبه ع كيف اخد الدوا ل قبل استشارة الطبيب قبل تخطيط للحمل ممنوع الدوا مابصير لازم كل شهر مراقبة تجربة كاشف الحمل لازم

Original:
هي حبة صغيرة مهدئة للقلق اللي بيجي قبل العمليات الجراحية. طريقة استخدامها سهلة، بتحط حبة وحدة تحت لسانك وخليها تذوب لحالها قبل العملية بساعة تقريبا. مفعولها سريع ورح تساعدك تسترخي وتهدى. أهم تحذير إنو بعد ما تاخذها ممنوع تسوق أو تعمل أي شي بيحتاج تركيز، ولازم يكون في حدا مرافق معك.
Gloss:
دوا الهدف منو القلق نوقفو او نخففو قبل العملية كيف الدوا الدوا هو لسان تحت يعني موجودة الحبة بعدها بتذوب وبتختفي قبل العملية بتساعدنا ل نهدي وبسرعة بتذوب الحبة وبترتاح والدوا مشان يساعدنا مشان نرتاح مهم الدوا وبعد عمل او سوق مابصير او عمل في تركيز مابصير لازم مع الشخص شخص شاهد او مرافق

Original:
خدي حبة كل 8 ساعات بعد الأكل لمدة خمسة أيام
Gloss:
حبة وحدة كل 8 ساعات بعد الاكل مدة 5 يوم

Now convert this input into the same dataset style.

Input:
{approved_text}

Generated Gloss:"""


class SignGenerationError(Exception):
    def __init__(self, message, *, safe_message=None):
        super().__init__(message)
        self.safe_message = safe_message or sanitize_transcription_error(message)


def log_prescription_access(prescription, user, access_type):
    return PrescriptionAccessLog.objects.create(
        prescription=prescription,
        accessed_by=user,
        access_type=access_type,
    )


def transcribe_prescription_item(prescription_item, *, requested_by, force=False):
    if not prescription_item.instructions_audio:
        raise ValueError('Cannot transcribe an item without instructions audio.')

    if (
        prescription_item.transcription_status == TranscriptionStatusChoices.COMPLETED
        and not force
    ):
        return prescription_item

    prescription_item.transcription_status = TranscriptionStatusChoices.PROCESSING
    prescription_item.transcription_requested_at = timezone.now()
    prescription_item.transcription_error_message = ''
    prescription_item.save(
        update_fields=[
            'transcription_status',
            'transcription_requested_at',
            'transcription_error_message',
            'updated_at',
        ]
    )

    backend = get_transcription_backend()
    try:
        result = backend.transcribe(prescription_item=prescription_item)
    except Exception as exc:
        prescription_item.transcription_status = TranscriptionStatusChoices.FAILED
        prescription_item.transcription_provider = getattr(backend, 'provider_name', '')
        prescription_item.transcription_completed_at = timezone.now()
        prescription_item.transcription_error_message = str(exc)
        prescription_item.save(
            update_fields=[
                'transcription_status',
                'transcription_provider',
                'transcription_completed_at',
                'transcription_error_message',
                'updated_at',
            ]
        )
        raise

    prescription_item.instructions_transcript_raw = result.raw_text
    if not prescription_item.instructions_transcript_edited:
        prescription_item.instructions_transcript_edited = result.raw_text
    prescription_item.transcription_status = TranscriptionStatusChoices.COMPLETED
    prescription_item.transcription_provider = result.provider_name
    prescription_item.transcription_completed_at = timezone.now()
    prescription_item.transcription_error_message = ''
    prescription_item.save(
        update_fields=[
            'instructions_transcript_raw',
            'instructions_transcript_edited',
            'transcription_status',
            'transcription_provider',
            'transcription_completed_at',
            'transcription_error_message',
            'updated_at',
        ]
    )
    log_prescription_access(
        prescription_item.prescription,
        requested_by,
        PrescriptionAccessTypeChoices.TRANSCRIBE,
    )
    return prescription_item


def generate_sign_gloss(approved_text):
    from django.conf import settings

    if not settings.GEMINI_API_KEY:
        raise SignGenerationError("Gemini API key is not configured.")

    prompt = SIGN_GLOSS_PROMPT_TEMPLATE.format(approved_text=approved_text)
    try:
        genai, _types = get_gemini_modules()
        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        response = client.models.generate_content(
            model=settings.GEMINI_SIGN_MODEL,
            contents=prompt,
        )
    except Exception as exc:
        raise SignGenerationError(
            str(exc),
            safe_message=sanitize_transcription_error(str(exc)),
        ) from exc

    gloss_text = getattr(response, "text", None)
    if not gloss_text or not str(gloss_text).strip():
        raise SignGenerationError("Gemini returned an empty sign gloss.")
    return {
        "provider": "gemini",
        "model": settings.GEMINI_SIGN_MODEL,
        "gloss_text": str(gloss_text).strip(),
    }


def mark_prescription_item_sign_processing(item):
    item.sign_status = SignStatusChoices.PROCESSING
    item.save(update_fields=["sign_status", "updated_at"])
    return item


def mark_prescription_item_sign_completed(item, gloss_text):
    item.supporting_text = gloss_text
    item.sign_status = SignStatusChoices.COMPLETED
    item.save(update_fields=["supporting_text", "sign_status", "updated_at"])
    return item


def mark_prescription_item_sign_failed(item):
    item.sign_status = SignStatusChoices.FAILED
    item.save(update_fields=["sign_status", "updated_at"])
    return item
