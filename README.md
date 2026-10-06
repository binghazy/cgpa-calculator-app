# Ghazy CGPA Calculator

Run from this folder:

```powershell
python -m pip install -r requirements.txt
python -m streamlit run cgpa_calculator.py
```

Run the server from a terminal with internet access. A restricted development
sandbox can allow the local page to load while blocking outbound Gemini requests
with Windows error 10013. This is a server networking issue, not an invalid key.
The development instance with network access is at `http://127.0.0.1:8502`.

The included `Student_Transcript_Data (1).xlsx` loads automatically, regardless of the terminal's working directory. The app reads all 53 course attempts. Its all-attempt CGPA is **2.633** (371.3 grade points / 141 graded credits); unique passed courses earn **137 credits**.

## Working with your record

- Open **Manage workbook** in the sidebar to load another `.xlsx`.
- Use **Courses & grades** to select a semester/worksheet, edit cells, add rows, or select rows for deletion. Click **Save course changes** to update the calculations.
- **Find a course** searches the entire record without filtering the editable table. **Add a course** provides a simple form, and **Undo last course change** reverses the last save or addition. Save table edits before switching groups or using another form.
- **Planning & analytics** lets you simulate your next semester's credits and average grade without modifying your transcript.
- Use **Download current record (.xlsx)** to keep edits. Working changes live in the browser session; the source workbook is never overwritten.
- **Workbook data** shows import counts, warnings, and every original worksheet cell, including additional columns and formulas.
- **Restore imported record** discards session edits and restores the last imported workbook.

## Import and calculation rules

Course tables require `Course Code`, `Credits (Units)`, and `Grade` columns; common alternatives such as `Code`, `Credits`, and `Letter Grade` also work. An optional `Semester` or `Term` column supplies grouping; blank term cells continue the preceding term. Without that column, the worksheet name is used. No semester chronology is inferred from row order.

All attempts are retained, including repeated course codes. All letter-graded attempts contribute to CGPA, including F. P contributes only to earned credits. The supplied LAN 21 row has N/A credits: it remains visible with zero numeric credits and an import warning. Earned credits count each passed course code once, using its largest passed credit value. University-specific retake replacement policies are not assumed.

The app uses the displayed 4.0 grade scale. Workbook Grade Points values are retained and checked against the scale. Unknown grades, missing numeric credits on graded courses, and invalid course rows reject an import without replacing your working record. Non-course worksheets remain visible and are reported. Excel formulas require saved calculated values for course fields; recalculate and save in Excel if necessary.

Planning scenarios explicitly assume replacement of listed attempts by A grades. They do not change the transcript.

## Gemini chat assistant

Open **AI Assistant** for a WhatsApp-style conversation: green outgoing bubbles, white incoming bubbles, timestamps, automatic scrolling, and a message composer below the conversation. Press Enter to send or Shift+Enter for a new line. Suggested questions fill the composer without sending. **Clear chat** clears the conversation; failed messages offer **Retry message**.

In the sidebar, open **Gemini settings**:

1. Get a key from [Google AI Studio](https://aistudio.google.com/apikey).
2. Paste it into the password-protected **Gemini API key** field.
3. Select a model and click **Test connection**.

Available choices: **Gemini 3.1 Flash-Lite** (default), **Gemini 3 Flash Preview**, **Gemini 2.5 Flash**, and **Gemini 2.5 Flash-Lite**. Preview availability and quotas vary by project. Google's [pricing page](https://ai.google.dev/gemini-api/docs/pricing) lists current free-tier eligibility. Use a project without billing for free-tier-only usage; the app cannot enforce Google billing settings. There is no automatic model switching or paid fallback.

Alternatively, copy `.env.example` to `.env` beside the app and add your key:

```dotenv
GEMINI_API_KEY=your_key_here
```

The app reads `GEMINI_API_KEY` from the environment or `.env`. Sidebar keys stay in session state and are not written to disk. Never commit `.env`.

Sending a message shares your current academic record and up to 12 previous completed exchanges with Google. Free-tier data may be used to improve Google's products. The conversation stays in browser session state and is cleared on workbook import or restore. Without a key, the offline guide remains available for GPA calculations and simple planning questions.

The client uses Google's native `generateContent` API. Keys are sent in the `x-goog-api-key` header, never in URLs. Authentication errors, quota limits, blocked responses, unavailable models, and connection failures appear as retryable chat errors. The connection test sends only a short test prompt, not the transcript.

## Verification

```powershell
python -m unittest -v test_app.py test_gemini.py
```

Tests cover workbook reconciliation, multi-sheet imports, weighted GPA, export/reimport, editing/search/undo, chat sending and retry, conversation history, and Gemini requests and errors. A live connection test succeeded with Gemini 3.1 Flash-Lite. Gemini 3 Flash Preview returned a temporary 503 during that check. Keys containing periods and copied Markdown escapes are supported. Visual browser checks were unavailable in the development environment.
