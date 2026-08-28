import { useEffect, useState } from "react";
import {
  Building2,
  Download,
  Edit,
  Mail,
  Plus,
  Save,
  Send,
  Sparkles,
  User,
} from "lucide-react";

import {
  fetchEvents,
  fetchSpecialists,
  fetchUniversityContacts,
  generateEmail,
  generateIcs,
  generateQrAsset,
  type CppEvent,
  type QrCodeAsset,
  type OutreachEmailResponse,
  type Specialist,
  type UniversityContact,
} from "@/lib/api";
import { QRCodeCard } from "@/components/QRCodeCard";
import { CrawlerFeed } from "@/components/CrawlerFeed";

type Template = {
  id: number;
  name: string;
  category: "volunteer" | "university" | "student";
  subject: string;
  body: string;
};

type RecentEmail = {
  to: string;
  subject: string;
  date: string;
  status: string;
};

const templates: Template[] = [
  {
    id: 1,
    name: "Volunteer Invitation",
    category: "volunteer",
    subject: "Invitation: {{EVENT_NAME}}",
    body: "Use AI Generate Email to fill this draft with live match details.",
  },
  {
    id: 2,
    name: "University Partnership Proposal",
    category: "university",
    subject: "Partnership Opportunity: Insights Association West Chapter",
    body: "Use this when reaching out to a university point of contact.",
  },
  {
    id: 3,
    name: "Student Member Welcome",
    category: "student",
    subject: "Welcome to Insights Association",
    body: "Use this for post-event membership follow-up.",
  },
];

function downloadTextFile(filename: string, contents: string, type: string) {
  const blob = new Blob([contents], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export function Outreach() {
  const [selectedTemplate, setSelectedTemplate] = useState<Template>(templates[0]);
  const [editMode, setEditMode] = useState(false);
  const [subject, setSubject] = useState(templates[0].subject);
  const [body, setBody] = useState(templates[0].body);
  const [showNewTemplate, setShowNewTemplate] = useState(false);
  const [specialists, setSpecialists] = useState<Specialist[]>([]);
  const [events, setEvents] = useState<CppEvent[]>([]);
  const [selectedSpeaker, setSelectedSpeaker] = useState("");
  const [selectedEvent, setSelectedEvent] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [qrBusy, setQrBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [qrError, setQrError] = useState<string | null>(null);
  const [recentEmails, setRecentEmails] = useState<RecentEmail[]>([]);
  const [lastGenerated, setLastGenerated] = useState<OutreachEmailResponse | null>(null);
  const [qrAsset, setQrAsset] = useState<QrCodeAsset | null>(null);
  const [universityContacts, setUniversityContacts] = useState<UniversityContact[]>([]);

  useEffect(() => {
    let active = true;

    Promise.all([fetchSpecialists(), fetchEvents(), fetchUniversityContacts()])
      .then(([specialistResult, eventResult, uniContacts]) => {
        if (!active) {
          return;
        }
        const specialistRows = specialistResult.data;
        const eventRows = eventResult.data;
        setSpecialists(specialistRows);
        setEvents(eventRows);
        setSelectedSpeaker(specialistRows[0]?.name ?? "");
        setSelectedEvent(eventRows[0]?.["Event / Program"] ?? "");
        setUniversityContacts(uniContacts);
      })
      .catch((err: unknown) => {
        if (active) {
          setError(err instanceof Error ? err.message : "Failed to load outreach data.");
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, []);

  const selectedEventRow =
    events.find((event) => event["Event / Program"] === selectedEvent) ?? null;

  useEffect(() => {
    setQrAsset(null);
    setQrError(null);
  }, [selectedSpeaker, selectedEvent]);

  const handleTemplateSelect = (template: Template) => {
    setSelectedTemplate(template);
    setSubject(template.subject);
    setBody(template.body);
    setEditMode(false);
  };

  const handleAIEnhance = () => {
    setBody((current) =>
      `${current}\n\n[Enhanced note] Add a precise CTA and mention the host's published audience.`,
    );
  };

  const handleGenerateEmail = async () => {
    if (!selectedSpeaker || !selectedEvent) {
      return;
    }

    setBusy(true);
    setError(null);

    try {
      const isUniRecipient = selectedSpeaker.startsWith("__uni__");
      const effectiveName = isUniRecipient
        ? selectedSpeaker.replace(/^__uni__/, "").split("|")[0]
        : selectedSpeaker;
      const generated = await generateEmail(effectiveName, selectedEvent, {
        request_source: "ia_west_admin",
      });
      setLastGenerated(generated);
      setSubject(generated.email_data.subject_line);
      setBody(
        `${generated.email_data.greeting}\n\n${generated.email_data.body}\n\n${generated.email_data.closing}`,
      );
      setRecentEmails((previous) => [
        {
          to: effectiveName,
          subject: generated.email_data.subject_line,
          date: new Date().toLocaleDateString("en-US", {
            month: "short",
            day: "numeric",
            year: "numeric",
          }),
          status: "Generated",
        },
        ...previous,
      ].slice(0, 6));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to generate email.");
    } finally {
      setBusy(false);
    }
  };

  const handleDownloadIcs = async () => {
    if (!selectedEvent) {
      return;
    }

    setBusy(true);
    setError(null);

    try {
      const payload = await generateIcs(
        selectedEvent,
        undefined,
        selectedEventRow?.["Host / Unit"],
        lastGenerated?.email_data.body,
      );
      downloadTextFile("ia-west-event.ics", payload.ics_content, "text/calendar");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to generate ICS file.");
    } finally {
      setBusy(false);
    }
  };

  const handleGenerateQr = async () => {
    if (!selectedSpeaker || !selectedEvent) {
      return;
    }

    setQrBusy(true);
    setQrError(null);

    try {
      const asset = await generateQrAsset(selectedSpeaker, selectedEvent);
      if (!asset) {
        setQrAsset(null);
        setQrError("The QR service returned no asset for the selected speaker-event pair.");
        return;
      }
      setQrAsset(asset);
    } catch (err: unknown) {
      setQrAsset(null);
      setQrError(err instanceof Error ? err.message : "Failed to generate QR asset.");
    } finally {
      setQrBusy(false);
    }
  };

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      <div>
        <div className="flex items-center gap-3 mb-2">
          <div className="w-10 h-10 bg-gradient-to-br from-blue-500 to-blue-500 rounded-lg flex items-center justify-center">
            <Mail className="w-6 h-6 text-white" />
          </div>
          <h1 className="text-3xl font-semibold text-gray-900">Outreach & Communications</h1>
        </div>
        <p className="text-gray-600">Generate live outreach copy from the backend email service.</p>
      </div>

      {error ? (
        <div className="bg-red-50 border border-red-200 rounded-xl p-6 text-red-700">{error}</div>
      ) : null}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1 space-y-4">
          <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-gray-900">Templates</h3>
              <button
                onClick={() => setShowNewTemplate(true)}
                className="p-2 bg-blue-100 text-blue-600 rounded-lg hover:bg-blue-200 transition-colors"
                aria-label="Add new template"
              >
                <Plus className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-2">
              {templates.map((template) => (
                <button
                  key={template.id}
                  onClick={() => handleTemplateSelect(template)}
                  className={`w-full text-left p-3 rounded-lg transition-colors ${
                    selectedTemplate.id === template.id
                      ? "bg-blue-50 border border-blue-200"
                      : "bg-gray-50 border border-transparent hover:bg-gray-100"
                  }`}
                >
                  <p className="font-medium text-gray-900 text-sm mb-1">{template.name}</p>
                  <div className="flex items-center gap-2">
                    {template.category === "volunteer" ? (
                      <span className="flex items-center gap-1 px-2 py-0.5 bg-blue-100 text-blue-700 text-xs rounded-full">
                        <User className="w-3 h-3" />
                        Volunteer
                      </span>
                    ) : template.category === "university" ? (
                      <span className="flex items-center gap-1 px-2 py-0.5 bg-blue-100 text-blue-700 text-xs rounded-full">
                        <Building2 className="w-3 h-3" />
                        University
                      </span>
                    ) : (
                      <span className="px-2 py-0.5 bg-green-100 text-green-700 text-xs rounded-full">
                        Student
                      </span>
                    )}
                  </div>
                </button>
              ))}
            </div>
          </div>

          <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
            <h3 className="font-semibold text-gray-900 mb-4">Quick Actions</h3>
            <div className="space-y-2">
              <button
                onClick={() => void handleGenerateEmail()}
                disabled={loading || busy}
                className="w-full flex items-center gap-3 p-3 bg-blue-50 text-blue-700 rounded-lg hover:bg-blue-100 transition-colors disabled:opacity-60"
              >
                <Sparkles className="w-5 h-5" />
                <span className="font-medium">AI Generate Email</span>
              </button>
              <button
                onClick={() => void handleDownloadIcs()}
                disabled={loading || busy}
                className="w-full flex items-center gap-3 p-3 bg-blue-50 text-blue-700 rounded-lg hover:bg-blue-100 transition-colors disabled:opacity-60"
              >
                <Download className="w-5 h-5" />
                <span className="font-medium">Download ICS Invite</span>
              </button>
            </div>
          </div>

          {/* Web Intelligence — left column so it persists visually alongside other menus */}
          <CrawlerFeed />
        </div>

        <div className="lg:col-span-2 bg-white rounded-xl p-6 border border-gray-200 shadow-sm">
          <div className="flex items-center justify-between mb-6">
            <h3 className="text-xl font-semibold text-gray-900">{selectedTemplate.name}</h3>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setEditMode((current) => !current)}
                className="flex items-center gap-2 px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors"
              >
                <Edit className="w-4 h-4" />
                {editMode ? "Preview" : "Edit"}
              </button>
            </div>
          </div>

          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Recipient</label>
                <select
                  value={selectedSpeaker}
                  onChange={(event) => setSelectedSpeaker(event.target.value)}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <optgroup label="IA West Volunteers">
                    {specialists.map((speaker) => (
                      <option key={speaker.name} value={speaker.name}>
                        {speaker.name}
                      </option>
                    ))}
                  </optgroup>
                  {selectedTemplate.category === "university" && universityContacts.length > 0 && (
                    <optgroup label="University Contacts (CPP)">
                      {universityContacts.map((c, i) => (
                        <option key={`${c.name}-${i}`} value={`__uni__${c.name}|${c.event_name}`}>
                          CPP – {c.name} ({c.event_name})
                        </option>
                      ))}
                    </optgroup>
                  )}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Event</label>
                <select
                  value={selectedEvent}
                  onChange={(event) => setSelectedEvent(event.target.value)}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  {events.map((event) => (
                    <option key={event["Event / Program"]} value={event["Event / Program"]}>
                      {event["Event / Program"]}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">To:</label>
              <div className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-gray-50 text-gray-700">
                {selectedSpeaker || "Select a volunteer"}
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Subject:</label>
              {editMode ? (
                <input
                  type="text"
                  value={subject}
                  onChange={(event) => setSubject(event.target.value)}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              ) : (
                <div className="px-4 py-2 bg-gray-50 rounded-lg text-gray-900">{subject}</div>
              )}
            </div>

            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="block text-sm font-medium text-gray-700">Message:</label>
                {editMode ? (
                  <button
                    onClick={handleAIEnhance}
                    className="flex items-center gap-1 text-sm text-blue-600 hover:text-blue-700"
                  >
                    <Sparkles className="w-4 h-4" />
                    AI Enhance
                  </button>
                ) : null}
              </div>
              {editMode ? (
                <textarea
                  value={body}
                  onChange={(event) => setBody(event.target.value)}
                  rows={16}
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono text-sm"
                />
              ) : (
                <div className="px-4 py-3 bg-gray-50 rounded-lg text-gray-900 whitespace-pre-wrap min-h-[400px]">
                  {body}
                </div>
              )}
            </div>

            <div className="bg-blue-50 rounded-lg p-4 border border-blue-200">
              <p className="text-sm font-medium text-blue-900 mb-2">Live context</p>
              <p className="text-sm text-blue-800">
                Event host: {selectedEventRow?.["Host / Unit"] || "Not listed"}
              </p>
              <p className="text-sm text-blue-800">
                Audience: {selectedEventRow?.["Primary Audience"] || "Not listed"}
              </p>
            </div>

            <QRCodeCard
              asset={qrAsset}
              loading={loading || qrBusy}
              error={qrError}
              title="Referral QR"
              description="Generate a deterministic QR asset for the current outreach pair."
              onPrimaryAction={() => void handleGenerateQr()}
            />

            <div className="flex items-center gap-3 pt-4">
              <button
                onClick={() => void handleGenerateEmail()}
                disabled={busy || loading}
                className="flex-1 flex items-center justify-center gap-2 px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-medium disabled:opacity-60"
              >
                <Send className="w-5 h-5" />
                {busy ? "Working..." : "Generate / Refresh"}
              </button>
              <button className="px-6 py-3 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors font-medium flex items-center gap-2">
                <Save className="w-5 h-5" />
                Save Draft
              </button>
              <button
                onClick={() => void handleDownloadIcs()}
                disabled={busy || loading}
                className="px-6 py-3 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors font-medium flex items-center gap-2 disabled:opacity-60"
              >
                <Download className="w-5 h-5" />
                ICS
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="bg-white rounded-xl p-6 border border-gray-200 shadow-sm">
        <h3 className="text-xl font-semibold text-gray-900 mb-4">Recent Emails</h3>
        <div className="space-y-3">
          {recentEmails.length === 0 ? (
            <div className="rounded-lg border border-dashed border-gray-300 p-6 text-center text-gray-600">
              Generated outreach drafts will appear here.
            </div>
          ) : (
            recentEmails.map((email, index) => (
              <div
                key={`${email.to}-${index}`}
                className="flex items-center justify-between p-4 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors"
              >
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-1">
                    <p className="font-medium text-gray-900">{email.to}</p>
                    <span className="px-2 py-0.5 text-xs rounded-full bg-blue-100 text-blue-700">
                      {email.status}
                    </span>
                  </div>
                  <p className="text-sm text-gray-600">{email.subject}</p>
                </div>
                <p className="text-sm text-gray-500">{email.date}</p>
              </div>
            ))
          )}
        </div>
      </div>

      {showNewTemplate ? (
        <div
          className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
          onClick={() => setShowNewTemplate(false)}
          onKeyDown={(event) => { if (event.key === "Escape") setShowNewTemplate(false); }}
          role="presentation"
        >
          <div
            className="bg-white rounded-xl p-8 max-w-2xl w-full"
            onClick={(event) => event.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="new-template-title"
          >
            <h2 id="new-template-title" className="text-2xl font-semibold text-gray-900 mb-6">Create New Template</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Template Name</label>
                <input
                  type="text"
                  placeholder="e.g. Event Confirmation"
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg"
                />
              </div>
              <div className="flex gap-3 pt-4">
                <button
                  onClick={() => setShowNewTemplate(false)}
                  className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg font-medium"
                >
                  Create Template
                </button>
                <button
                  onClick={() => setShowNewTemplate(false)}
                  className="px-4 py-2 border border-gray-300 text-gray-700 rounded-lg font-medium"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}

    </div>
  );
}
