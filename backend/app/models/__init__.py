from app.models.admin import City, ClinicGroup, Province, Referral  # noqa: F401
from app.models.audit import AccessEvent, AuditLog  # noqa: F401
from app.models.availability import AvailabilityException, WeeklyRule  # noqa: F401
from app.models.booking import Appointment, SlotClaim  # noqa: F401
from app.models.catalog import (  # noqa: F401
    Consultant,
    Credential,
    Service,
    Specialty,
    VerificationReview,
)
from app.models.clinical import (  # noqa: F401
    ClinicalRecord,
    Encounter,
    EncounterAmendment,
    EncounterNote,
    Questionnaire,
    QuestionnaireVersion,
    RecordFile,
    Submission,
)
from app.models.consents import Consent, ConsentVersion  # noqa: F401
from app.models.content import Content, ContentRevision, ContentTopic  # noqa: F401
from app.models.core import Applicant, AuthSession, OtpChallenge, Profile, User  # noqa: F401
from app.models.edu import (  # noqa: F401
    AccessGrant,
    Certificate,
    Course,
    CourseEnrollment,
    CourseExam,
    CourseModule,
    ExamAnswer,
    ExamAttempt,
    ExamQuestion,
    Lesson,
    LessonProgress,
    LessonVersion,
)
from app.models.feedback import (  # noqa: F401
    SupportTicket,
    SurveyResponse,
    TicketMessage,
)
from app.models.files import File  # noqa: F401
from app.models.finance import (  # noqa: F401
    Account,
    Discount,
    DiscountRedemption,
    Invoice,
    InvoiceItem,
    JournalEntry,
    JournalLine,
    Order,
    Organization,
    OrganizationContract,
    OrganizationMember,
    Payment,
    Refund,
    RefundRequest,
    Settlement,
    Wallet,
    WalletEntry,
)
from app.models.notify import (  # noqa: F401
    CommunicationPreference,
    Message,
    MessageThread,
    MessageThreadMember,
    Notification,
    NotificationEvent,
)
from app.models.org import Branch, BranchServiceOffering, Clinic  # noqa: F401
from app.models.pricing import Tariff, TariffVersion  # noqa: F401
from app.models.rbac import Permission, Role, RolePermission, UserRole  # noqa: F401
from app.models.topics import Topic  # noqa: F401
