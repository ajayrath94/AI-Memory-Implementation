// Words for the newer screens — the shortcut sheets, "Kahan milega?", the
// buttons under a message, the calendar — in every language the app offers.
//
// strings.ts holds one long table per language; these screens keep a label
// and the sentence it sends side by side, which reads better as one entry
// with nine translations. English is the fallback, as in useT. Only English,
// Hinglish and Hindi are checked by a native speaker (VERIFIED in strings.ts);
// the rest should be read by one before anyone relies on them.

export type Code = 'en' | 'hl' | 'hi' | 'pa' | 'gu' | 'mr' | 'bn' | 'ta' | 'te'
export type Words = { en: string } & Partial<Record<Exclude<Code, 'en'>, string>>

const CODE: Record<string, Code> = {
  english: 'en', hinglish: 'hl', hindi: 'hi', punjabi: 'pa', gujarati: 'gu',
  marathi: 'mr', bengali: 'bn', tamil: 'ta', telugu: 'te',
}

export function codeOf(lang: string): Code {
  return CODE[(lang || '').toLowerCase()] || 'en'
}

/** The words in her language (English when missing), with {name} filled. */
export function pick(w: Words, lang: string, vars?: Record<string, string | number>): string {
  let s = w[codeOf(lang)] ?? w.en
  if (vars) for (const [k, v] of Object.entries(vars)) s = s.split(`{${k}}`).join(String(v))
  return s
}

/** One of a set of nine-language lists (weekdays, months). */
export function pickList(table: Partial<Record<Code, string[]>> & { en: string[] }, lang: string): string[] {
  return table[codeOf(lang)] ?? table.en
}

// ── buttons under a message ──────────────────────────────────────────────
export const LINK = {
  map:     { en: '{name} — open map', hl: '{name} — naksha kholo', hi: '{name} — नक्शा खोलो',
             pa: '{name} — ਨਕਸ਼ਾ ਖੋਲ੍ਹੋ', gu: '{name} — નકશો ખોલો', mr: '{name} — नकाशा उघडा',
             bn: '{name} — ম্যাপ খুলুন', ta: '{name} — வரைபடத்தைத் திற', te: '{name} — మ్యాప్ తెరవండి' },
  mapBare: { en: 'Open map', hl: 'Naksha kholo', hi: 'नक्शा खोलो', pa: 'ਨਕਸ਼ਾ ਖੋਲ੍ਹੋ',
             gu: 'નકશો ખોલો', mr: 'नकाशा उघडा', bn: 'ম্যাপ খুলুন', ta: 'வரைபடத்தைத் திற',
             te: 'మ్యాప్ తెరవండి' },
  call:    { en: '{name} — call', hl: '{name} — phone karo', hi: '{name} — फ़ोन करो',
             pa: '{name} — ਫ਼ੋਨ ਕਰੋ', gu: '{name} — ફોન કરો', mr: '{name} — फोन करा',
             bn: '{name} — ফোন করুন', ta: '{name} — அழை', te: '{name} — ఫోన్ చేయండి' },
  news:    { en: '{name} — read the full story', hl: '{name} — poori khabar padho',
             hi: '{name} — पूरी ख़बर पढ़ो', pa: '{name} — ਪੂਰੀ ਖ਼ਬਰ ਪੜ੍ਹੋ',
             gu: '{name} — આખા સમાચાર વાંચો', mr: '{name} — पूर्ण बातमी वाचा',
             bn: '{name} — পুরো খবর পড়ুন', ta: '{name} — முழுச் செய்தியைப் படி',
             te: '{name} — పూర్తి వార్త చదవండి' },
  newsName:{ en: 'News', hl: 'Khabar', hi: 'ख़बर', pa: 'ਖ਼ਬਰ', gu: 'સમાચાર', mr: 'बातमी',
             bn: 'খবর', ta: 'செய்தி', te: 'వార్త' },
  open:    { en: 'Open {name}', hl: '{name} kholo', hi: '{name} खोलो', pa: '{name} ਖੋਲ੍ਹੋ',
             gu: '{name} ખોલો', mr: '{name} उघडा', bn: '{name} খুলুন', ta: '{name} திற',
             te: '{name} తెరవండి' },
}

// ── the calendar ─────────────────────────────────────────────────────────
export const CAL = {
  morning:   { en: 'Morning', hl: 'Subah', hi: 'सुबह', pa: 'ਸਵੇਰ', gu: 'સવાર', mr: 'सकाळ', bn: 'সকাল', ta: 'காலை', te: 'ఉదయం' },
  afternoon: { en: 'Afternoon', hl: 'Dopahar', hi: 'दोपहर', pa: 'ਦੁਪਹਿਰ', gu: 'બપોર', mr: 'दुपार', bn: 'দুপুর', ta: 'மதியம்', te: 'మధ్యాహ్నం' },
  evening:   { en: 'Evening', hl: 'Shaam', hi: 'शाम', pa: 'ਸ਼ਾਮ', gu: 'સાંજ', mr: 'संध्याकाळ', bn: 'সন্ধ্যা', ta: 'மாலை', te: 'సాయంత్రం' },
  night:     { en: 'Night', hl: 'Raat', hi: 'रात', pa: 'ਰਾਤ', gu: 'રાત', mr: 'रात्र', bn: 'রাত', ta: 'இரவு', te: 'రాత్రి' },
  today:     { en: 'Today', hl: 'Aaj', hi: 'आज', pa: 'ਅੱਜ', gu: 'આજે', mr: 'आज', bn: 'আজ', ta: 'இன்று', te: 'ఈరోజు' },
  tomorrow:  { en: 'Tomorrow', hl: 'Kal', hi: 'कल', pa: 'ਕੱਲ੍ਹ', gu: 'આવતીકાલ', mr: 'उद्या', bn: 'কাল', ta: 'நாளை', te: 'రేపు' },
  // The row under each part of the day, and the sheet it opens. Hinglish and
  // Hindi name the part; the others say it plainly (the part is just above).
  addRow:    { en: '+ Add something', hl: '+ {part} mein kuch jodo', hi: '+ {part} में कुछ जोड़ो',
               pa: '+ ਕੁਝ ਜੋੜੋ', gu: '+ કંઈક ઉમેરો', mr: '+ काहीतरी जोडा', bn: '+ কিছু যোগ করুন',
               ta: '+ ஏதாவது சேர்', te: '+ ఏదైనా జోడించండి' },
  partHead:  { en: 'What would you like to add?', hl: '{part} mein kya hai?', hi: '{part} में क्या है?',
               pa: 'ਕੀ ਜੋੜਨਾ ਹੈ?', gu: 'શું ઉમેરવું છે?', mr: 'काय जोडायचं आहे?', bn: 'কী যোগ করবেন?',
               ta: 'என்ன சேர்க்க வேண்டும்?', te: 'ఏం జోడించాలి?' },
  addHead:   { en: 'What would you like to add?', hl: 'Kya jodna hai?', hi: 'क्या जोड़ना है?',
               pa: 'ਕੀ ਜੋੜਨਾ ਹੈ?', gu: 'શું ઉમેરવું છે?', mr: 'काय जोडायचं आहे?', bn: 'কী যোগ করবেন?',
               ta: 'என்ன சேர்க்க வேண்டும்?', te: 'ఏం జోడించాలి?' },
  reminderHead: { en: 'Reminder from {bot}', hl: '{bot} ka reminder', hi: '{bot} का रिमाइंडर',
               pa: '{bot} ਦੀ ਯਾਦ', gu: '{bot}નું રિમાઇન્ડર', mr: '{bot}चं रिमाइंडर', bn: '{bot}-র রিমাইন্ডার',
               ta: '{bot} நினைவூட்டல்', te: '{bot} రిమైండర్' },
  changeHead:{ en: 'Change', hl: 'Badlo', hi: 'बदलो', pa: 'ਬਦਲੋ', gu: 'બદલો', mr: 'बदला', bn: 'বদলান', ta: 'மாற்று', te: 'మార్చండి' },
  whatQ:     { en: 'What is it?', hl: 'Kya hai?', hi: 'क्या है?', pa: 'ਕੀ ਹੈ?', gu: 'શું છે?', mr: 'काय आहे?', bn: 'কী আছে?', ta: 'என்ன?', te: 'ఏమిటి?' },
  whatBody:  { en: 'Please write what it is.', hl: 'Thoda likh dijiye — kya hai.', hi: 'थोड़ा लिख दीजिए — क्या है।',
               pa: 'ਥੋੜ੍ਹਾ ਲਿਖ ਦਿਓ — ਕੀ ਹੈ।', gu: 'થોડું લખી દો — શું છે.', mr: 'थोडं लिहा — काय आहे.',
               bn: 'একটু লিখে দিন — কী আছে।', ta: 'என்னவென்று கொஞ்சம் எழுதுங்கள்.', te: 'ఏమిటో కొంచెం రాయండి.' },
  pastQ:     { en: 'That time has passed', hl: 'Yeh samay nikal gaya', hi: 'यह समय निकल गया',
               pa: 'ਇਹ ਸਮਾਂ ਲੰਘ ਗਿਆ', gu: 'આ સમય વીતી ગયો', mr: 'ही वेळ निघून गेली', bn: 'এই সময় পেরিয়ে গেছে',
               ta: 'இந்த நேரம் கடந்துவிட்டது', te: 'ఈ సమయం దాటిపోయింది' },
  pastBody:  { en: 'Please choose a later time.', hl: 'Aage ka koi samay chuniye.', hi: 'आगे का कोई समय चुनिए।',
               pa: 'ਅੱਗੇ ਦਾ ਕੋਈ ਸਮਾਂ ਚੁਣੋ।', gu: 'આગળનો કોઈ સમય પસંદ કરો.', mr: 'पुढची एखादी वेळ निवडा.',
               bn: 'পরের কোনো সময় বেছে নিন।', ta: 'பிந்தைய நேரத்தைத் தேர்ந்தெடுங்கள்.', te: 'తర్వాతి సమయం ఎంచుకోండి.' },
  thereQ:    { en: 'Already there', hl: 'Pehle se hai', hi: 'पहले से है', pa: 'ਪਹਿਲਾਂ ਹੀ ਹੈ', gu: 'પહેલેથી છે',
               mr: 'आधीच आहे', bn: 'আগে থেকেই আছে', ta: 'ஏற்கெனவே உள்ளது', te: 'ఇప్పటికే ఉంది' },
  thereBody: { en: '"{title}" is already on the calendar that day.', hl: '"{title}" us din pehle se calendar mein hai.',
               hi: '"{title}" उस दिन पहले से कैलेंडर में है।', pa: '"{title}" ਉਸ ਦਿਨ ਪਹਿਲਾਂ ਹੀ ਕੈਲੰਡਰ ਵਿੱਚ ਹੈ।',
               gu: '"{title}" તે દિવસે પહેલેથી કૅલેન્ડરમાં છે.', mr: '"{title}" त्या दिवशी आधीच कॅलेंडरमध्ये आहे.',
               bn: '"{title}" সেদিন আগে থেকেই ক্যালেন্ডারে আছে।', ta: '"{title}" அன்று ஏற்கெனவே நாட்காட்டியில் உள்ளது.',
               te: '"{title}" ఆ రోజు ఇప్పటికే క్యాలెండర్‌లో ఉంది.' },
  failQ:     { en: "Couldn't save", hl: 'Nahi ho paaya', hi: 'नहीं हो पाया', pa: 'ਨਹੀਂ ਹੋ ਸਕਿਆ', gu: 'થઈ શક્યું નહીં',
               mr: 'झालं नाही', bn: 'হল না', ta: 'முடியவில்லை', te: 'కాలేదు' },
  failBody:  { en: 'Please try again in a little while.', hl: 'Thodi der baad phir koshish kijiye.',
               hi: 'थोड़ी देर बाद फिर कोशिश कीजिए।', pa: 'ਥੋੜ੍ਹੀ ਦੇਰ ਬਾਅਦ ਫਿਰ ਕੋਸ਼ਿਸ਼ ਕਰੋ।',
               gu: 'થોડી વાર પછી ફરી પ્રયત્ન કરો.', mr: 'थोड्या वेळाने पुन्हा प्रयत्न करा.',
               bn: 'একটু পরে আবার চেষ্টা করুন।', ta: 'சிறிது நேரம் கழித்து மீண்டும் முயலுங்கள்.',
               te: 'కొంచెం సేపయ్యాక మళ్ళీ ప్రయత్నించండి.' },
  removeQ:   { en: 'Remove it?', hl: 'Hata dein?', hi: 'हटा दें?', pa: 'ਹਟਾ ਦੇਈਏ?', gu: 'કાઢી નાખીએ?',
               mr: 'काढून टाकायचं?', bn: 'সরিয়ে দেব?', ta: 'நீக்கலாமா?', te: 'తీసేయాలా?' },
  removeBody:{ en: '"{title}" — its reminders will stop too.', hl: '"{title}" — iski yaad bhi band ho jayegi.',
               hi: '"{title}" — इसकी याद भी बंद हो जाएगी।', pa: '"{title}" — ਇਸਦੀ ਯਾਦ ਵੀ ਬੰਦ ਹੋ ਜਾਏਗੀ।',
               gu: '"{title}" — તેની યાદ પણ બંધ થઈ જશે.', mr: '"{title}" — याची आठवणही बंद होईल.',
               bn: '"{title}" — এর মনে করানোও বন্ধ হয়ে যাবে।', ta: '"{title}" — இதன் நினைவூட்டலும் நின்றுவிடும்.',
               te: '"{title}" — దీని గుర్తుచేయడం కూడా ఆగిపోతుంది.' },
  keep:      { en: 'Keep it', hl: 'Rehne do', hi: 'रहने दो', pa: 'ਰਹਿਣ ਦਿਓ', gu: 'રહેવા દો', mr: 'राहू द्या',
               bn: 'থাক', ta: 'இருக்கட்டும்', te: 'ఉండనివ్వండి' },
  remove:    { en: 'Remove', hl: 'Hata do', hi: 'हटा दो', pa: 'ਹਟਾ ਦਿਓ', gu: 'કાઢી નાખો', mr: 'काढून टाका',
               bn: 'সরিয়ে দিন', ta: 'நீக்கு', te: 'తీసేయండి' },
  remindTag: { en: "I'll remind you", hl: 'Yaad dilaungi', hi: 'याद दिलाऊँगी', pa: 'ਯਾਦ ਕਰਾਵਾਂਗੀ', gu: 'યાદ કરાવીશ',
               mr: 'आठवण करून देईन', bn: 'মনে করিয়ে দেব', ta: 'நினைவூட்டுவேன்', te: 'గుర్తు చేస్తాను' },
  whatLbl:   { en: 'What', hl: 'Kya hai', hi: 'क्या है', pa: 'ਕੀ ਹੈ', gu: 'શું છે', mr: 'काय आहे', bn: 'কী', ta: 'என்ன', te: 'ఏమిటి' },
  whenLbl:   { en: 'When', hl: 'Kab', hi: 'कब', pa: 'ਕਦੋਂ', gu: 'ક્યારે', mr: 'कधी', bn: 'কবে', ta: 'எப்போது', te: 'ఎప్పుడు' },
  example:   { en: 'e.g. Doctor, temple, son visiting', hl: 'Jaise: Doctor, mandir, beta aayega',
               hi: 'जैसे: डॉक्टर, मंदिर, बेटा आएगा', pa: 'ਜਿਵੇਂ: ਡਾਕਟਰ, ਮੰਦਰ, ਪੁੱਤਰ ਆਏਗਾ',
               gu: 'જેમ કે: ડૉક્ટર, મંદિર, દીકરો આવશે', mr: 'उदा: डॉक्टर, मंदिर, मुलगा येणार',
               bn: 'যেমন: ডাক্তার, মন্দির, ছেলে আসবে', ta: 'உதா: மருத்துவர், கோயில், மகன் வருகிறான்',
               te: 'ఉదా: డాక్టర్, గుడి, అబ్బాయి వస్తాడు' },
  kindLbl:   { en: 'What kind', hl: 'Kis tarah ka', hi: 'किस तरह का', pa: 'ਕਿਸ ਤਰ੍ਹਾਂ ਦਾ', gu: 'કેવા પ્રકારનું',
               mr: 'कोणत्या प्रकारचं', bn: 'কী ধরনের', ta: 'எந்த வகை', te: 'ఏ రకం' },
  kDoctor:   { en: 'Doctor', hl: 'Doctor', hi: 'डॉक्टर', pa: 'ਡਾਕਟਰ', gu: 'ડૉક્ટર', mr: 'डॉक्टर', bn: 'ডাক্তার', ta: 'மருத்துவர்', te: 'డాక్టర్' },
  kSocial:   { en: 'Meeting someone', hl: 'Milna', hi: 'मिलना', pa: 'ਮਿਲਣਾ', gu: 'મળવું', mr: 'भेट', bn: 'দেখা করা', ta: 'சந்திப்பு', te: 'కలవడం' },
  kFestival: { en: 'Festival / Puja', hl: 'Tyohar / Puja', hi: 'त्योहार / पूजा', pa: 'ਤਿਉਹਾਰ / ਪੂਜਾ', gu: 'તહેવાર / પૂજા',
               mr: 'सण / पूजा', bn: 'উৎসব / পুজো', ta: 'பண்டிகை / பூஜை', te: 'పండుగ / పూజ' },
  kPersonal: { en: 'Personal', hl: 'Apna', hi: 'अपना', pa: 'ਆਪਣਾ', gu: 'પોતાનું', mr: 'स्वतःचं', bn: 'নিজের', ta: 'சொந்தம்', te: 'సొంతం' },
  note:      { en: '🔔 {bot} will remind you — that morning, an hour before, and just before.',
               hl: '🔔 {bot} yaad dilayegi — subah, ek ghanta pehle, aur thik pehle.',
               hi: '🔔 {bot} याद दिलाएगी — सुबह, एक घंटा पहले, और ठीक पहले।',
               pa: '🔔 {bot} ਯਾਦ ਕਰਾਏਗੀ — ਸਵੇਰੇ, ਇੱਕ ਘੰਟਾ ਪਹਿਲਾਂ, ਤੇ ਠੀਕ ਪਹਿਲਾਂ।',
               gu: '🔔 {bot} યાદ કરાવશે — સવારે, એક કલાક પહેલાં, અને બરાબર પહેલાં.',
               mr: '🔔 {bot} आठवण करून देईल — सकाळी, एक तास आधी, आणि अगदी आधी.',
               bn: '🔔 {bot} মনে করিয়ে দেবে — সকালে, এক ঘণ্টা আগে, আর ঠিক আগে।',
               ta: '🔔 {bot} நினைவூட்டும் — காலையில், ஒரு மணி நேரம் முன்பு, சரியாக முன்பு.',
               te: '🔔 {bot} గుర్తు చేస్తుంది — ఉదయం, గంట ముందు, సరిగ్గా ముందు.' },
  saveNew:   { en: 'Save', hl: 'Rakh lo', hi: 'रख लो', pa: 'ਰੱਖ ਲਓ', gu: 'રાખી લો', mr: 'ठेवा', bn: 'রেখে দিন', ta: 'சேமி', te: 'దాచండి' },
  saveChange:{ en: 'Save changes', hl: 'Badal do', hi: 'बदल दो', pa: 'ਬਦਲ ਦਿਓ', gu: 'બદલી દો', mr: 'बदला', bn: 'বদলে দিন', ta: 'மாற்று', te: 'మార్చండి' },
  fromChat:  { en: 'This was set by talking to {bot}. To change it, just tell {bot}.',
               hl: 'Yeh {bot} se baat karke laga tha. Badalna ho toh {bot} ko bata dijiye.',
               hi: 'यह {bot} से बात करके लगा था। बदलना हो तो {bot} को बता दीजिए।',
               pa: 'ਇਹ {bot} ਨਾਲ ਗੱਲ ਕਰਕੇ ਲੱਗਿਆ ਸੀ। ਬਦਲਣਾ ਹੋਵੇ ਤਾਂ {bot} ਨੂੰ ਦੱਸ ਦਿਓ।',
               gu: 'આ {bot} સાથે વાત કરીને મુકાયું હતું. બદલવું હોય તો {bot}ને કહી દો.',
               mr: 'हे {bot}शी बोलून लावलं होतं. बदलायचं असेल तर {bot}ला सांगा.',
               bn: 'এটা {bot}-র সঙ্গে কথা বলে রাখা হয়েছিল। বদলাতে চাইলে {bot}-কে বলুন।',
               ta: 'இது {bot}-யுடன் பேசி வைக்கப்பட்டது. மாற்ற வேண்டுமானால் {bot}-யிடம் சொல்லுங்கள்.',
               te: 'ఇది {bot}తో మాట్లాడి పెట్టింది. మార్చాలంటే {bot}కి చెప్పండి.' },
  months:    { en: 'Months', hl: 'Mahine', hi: 'महीने', pa: 'ਮਹੀਨੇ', gu: 'મહિના', mr: 'महिने', bn: 'মাস', ta: 'மாதங்கள்', te: 'నెలలు' },
  goToday:   { en: 'Go to today', hl: 'Aaj par jao', hi: 'आज पर जाओ', pa: 'ਅੱਜ ਤੇ ਜਾਓ', gu: 'આજ પર જાઓ',
               mr: 'आजवर जा', bn: 'আজকে যান', ta: 'இன்றைக்குச் செல்', te: 'ఈరోజుకి వెళ్ళండి' },
}

// Weekdays, Sunday first: short (the day strip), full (the day's heading),
// and one-letter-ish heads for the month grid. Hinglish keeps what it had.
export const WEEKDAY_SHORT = {
  en: ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'],
  hl: ['Ravi', 'Som', 'Mangal', 'Budh', 'Guru', 'Shukra', 'Shani'],
  hi: ['रवि', 'सोम', 'मंगल', 'बुध', 'गुरु', 'शुक्र', 'शनि'],
  pa: ['ਐਤ', 'ਸੋਮ', 'ਮੰਗਲ', 'ਬੁੱਧ', 'ਵੀਰ', 'ਸ਼ੁੱਕਰ', 'ਸ਼ਨਿੱਚਰ'],
  gu: ['રવિ', 'સોમ', 'મંગળ', 'બુધ', 'ગુરુ', 'શુક્ર', 'શનિ'],
  mr: ['रवि', 'सोम', 'मंगळ', 'बुध', 'गुरु', 'शुक्र', 'शनि'],
  bn: ['রবি', 'সোম', 'মঙ্গল', 'বুধ', 'বৃহস্পতি', 'শুক্র', 'শনি'],
  ta: ['ஞாயிறு', 'திங்கள்', 'செவ்வாய்', 'புதன்', 'வியாழன்', 'வெள்ளி', 'சனி'],
  te: ['ఆది', 'సోమ', 'మంగళ', 'బుధ', 'గురు', 'శుక్ర', 'శని'],
}
export const WEEKDAY_FULL = {
  en: ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'],
  hi: ['रविवार', 'सोमवार', 'मंगलवार', 'बुधवार', 'गुरुवार', 'शुक्रवार', 'शनिवार'],
  pa: ['ਐਤਵਾਰ', 'ਸੋਮਵਾਰ', 'ਮੰਗਲਵਾਰ', 'ਬੁੱਧਵਾਰ', 'ਵੀਰਵਾਰ', 'ਸ਼ੁੱਕਰਵਾਰ', 'ਸ਼ਨਿੱਚਰਵਾਰ'],
  gu: ['રવિવાર', 'સોમવાર', 'મંગળવાર', 'બુધવાર', 'ગુરુવાર', 'શુક્રવાર', 'શનિવાર'],
  mr: ['रविवार', 'सोमवार', 'मंगळवार', 'बुधवार', 'गुरुवार', 'शुक्रवार', 'शनिवार'],
  bn: ['রবিবার', 'সোমবার', 'মঙ্গলবার', 'বুধবার', 'বৃহস্পতিবার', 'শুক্রবার', 'শনিবার'],
  ta: ['ஞாயிற்றுக்கிழமை', 'திங்கட்கிழமை', 'செவ்வாய்க்கிழமை', 'புதன்கிழமை', 'வியாழக்கிழமை', 'வெள்ளிக்கிழமை', 'சனிக்கிழமை'],
  te: ['ఆదివారం', 'సోమవారం', 'మంగళవారం', 'బుధవారం', 'గురువారం', 'శుక్రవారం', 'శనివారం'],
}
export const WEEKDAY_HEAD = {
  en: ['S', 'M', 'T', 'W', 'T', 'F', 'S'],
  hl: ['R', 'S', 'M', 'B', 'G', 'Sh', 'Sa'],
  hi: ['र', 'सो', 'मं', 'बु', 'गु', 'शु', 'श'],
  pa: ['ਐ', 'ਸੋ', 'ਮੰ', 'ਬੁ', 'ਵੀ', 'ਸ਼ੁ', 'ਸ਼'],
  gu: ['ર', 'સો', 'મં', 'બુ', 'ગુ', 'શુ', 'શ'],
  mr: ['र', 'सो', 'मं', 'बु', 'गु', 'शु', 'श'],
  bn: ['র', 'সো', 'ম', 'বু', 'বৃ', 'শু', 'শ'],
  ta: ['ஞா', 'தி', 'செ', 'பு', 'வி', 'வெ', 'ச'],
  te: ['ఆ', 'సో', 'మం', 'బు', 'గు', 'శు', 'శ'],
}
export const MONTH_NAMES = {
  en: ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'],
  hi: ['जनवरी', 'फ़रवरी', 'मार्च', 'अप्रैल', 'मई', 'जून', 'जुलाई', 'अगस्त', 'सितंबर', 'अक्टूबर', 'नवंबर', 'दिसंबर'],
  pa: ['ਜਨਵਰੀ', 'ਫ਼ਰਵਰੀ', 'ਮਾਰਚ', 'ਅਪ੍ਰੈਲ', 'ਮਈ', 'ਜੂਨ', 'ਜੁਲਾਈ', 'ਅਗਸਤ', 'ਸਤੰਬਰ', 'ਅਕਤੂਬਰ', 'ਨਵੰਬਰ', 'ਦਸੰਬਰ'],
  gu: ['જાન્યુઆરી', 'ફેબ્રુઆરી', 'માર્ચ', 'એપ્રિલ', 'મે', 'જૂન', 'જુલાઈ', 'ઑગસ્ટ', 'સપ્ટેમ્બર', 'ઑક્ટોબર', 'નવેમ્બર', 'ડિસેમ્બર'],
  mr: ['जानेवारी', 'फेब्रुवारी', 'मार्च', 'एप्रिल', 'मे', 'जून', 'जुलै', 'ऑगस्ट', 'सप्टेंबर', 'ऑक्टोबर', 'नोव्हेंबर', 'डिसेंबर'],
  bn: ['জানুয়ারি', 'ফেব্রুয়ারি', 'মার্চ', 'এপ্রিল', 'মে', 'জুন', 'জুলাই', 'আগস্ট', 'সেপ্টেম্বর', 'অক্টোবর', 'নভেম্বর', 'ডিসেম্বর'],
  ta: ['ஜனவரி', 'பிப்ரவரி', 'மார்ச்', 'ஏப்ரல்', 'மே', 'ஜூன்', 'ஜூலை', 'ஆகஸ்ட்', 'செப்டம்பர்', 'அக்டோபர்', 'நவம்பர்', 'டிசம்பர்'],
  te: ['జనవరి', 'ఫిబ్రవరి', 'మార్చి', 'ఏప్రిల్', 'మే', 'జూన్', 'జూలై', 'ఆగస్టు', 'సెప్టెంబర్', 'అక్టోబర్', 'నవంబర్', 'డిసెంబర్'],
}

// ── the list card in the chat ────────────────────────────────────────────
export const CARD = {
  count:   { en: '{done} of {total} done', hl: '{done}/{total} ho gaye', hi: '{done}/{total} हो गए', pa: '{done}/{total} ਹੋ ਗਏ',
             gu: '{done}/{total} થઈ ગયું', mr: '{done}/{total} झाले', bn: '{done}/{total} হয়ে গেছে', ta: '{done}/{total} முடிந்தது',
             te: '{done}/{total} అయ్యాయి' },
  start:   { en: '🛒 In the shop? One at a time', hl: '🛒 Dukaan mein? Ek ek karke', hi: '🛒 दुकान में? एक-एक करके',
             pa: '🛒 ਦੁਕਾਨ ਵਿੱਚ? ਇੱਕ-ਇੱਕ ਕਰਕੇ', gu: '🛒 દુકાનમાં? એક પછી એક', mr: '🛒 दुकानात? एकेक करून',
             bn: '🛒 দোকানে? একটা একটা করে', ta: '🛒 கடையிலா? ஒவ்வொன்றாக', te: '🛒 షాపులోనా? ఒక్కొక్కటిగా' },
  now:     { en: 'Now: {what}', hl: 'Abhi: {what}', hi: 'अभी: {what}', pa: 'ਹੁਣ: {what}', gu: 'હવે: {what}', mr: 'आता: {what}',
             bn: 'এখন: {what}', ta: 'இப்போது: {what}', te: 'ఇప్పుడు: {what}' },
  got:     { en: '✅ Got it', hl: '✅ Mil gaya', hi: '✅ मिल गया', pa: '✅ ਮਿਲ ਗਿਆ', gu: '✅ મળી ગયું', mr: '✅ मिळालं',
             bn: '✅ পেয়ে গেছি', ta: '✅ கிடைத்தது', te: '✅ దొరికింది' },
  skip:    { en: '⏭ Later', hl: '⏭ Baad mein', hi: '⏭ बाद में', pa: '⏭ ਬਾਅਦ ਵਿੱਚ', gu: '⏭ પછી', mr: '⏭ नंतर',
             bn: '⏭ পরে', ta: '⏭ பிறகு', te: '⏭ తర్వాత' },
  stop:    { en: 'Stop', hl: 'Bas', hi: 'बस', pa: 'ਬੱਸ', gu: 'બસ', mr: 'बस', bn: 'থাক', ta: 'போதும்', te: 'చాలు' },
  left:    { en: 'Still to get ({n}): {items}', hl: 'Baaki {n}: {items}', hi: 'बाकी {n}: {items}', pa: 'ਬਾਕੀ {n}: {items}',
             gu: 'બાકી {n}: {items}', mr: 'बाकी {n}: {items}', bn: 'বাকি {n}: {items}', ta: 'மீதம் {n}: {items}',
             te: 'మిగిలినవి {n}: {items}' },
  allDone: { en: 'Everything is done! 🎉', hl: 'Sab ho gaya! 🎉', hi: 'सब हो गया! 🎉', pa: 'ਸਭ ਹੋ ਗਿਆ! 🎉', gu: 'બધું થઈ ગયું! 🎉',
             mr: 'सगळं झालं! 🎉', bn: 'সব হয়ে গেছে! 🎉', ta: 'எல்லாம் முடிந்தது! 🎉', te: 'అన్నీ అయిపోయాయి! 🎉' },
  later:   { en: 'Keep the rest for later', hl: 'Baaki baad mein', hi: 'बाकी बाद में', pa: 'ਬਾਕੀ ਬਾਅਦ ਵਿੱਚ', gu: 'બાકી પછી',
             mr: 'बाकी नंतर', bn: 'বাকি পরে', ta: 'மீதி பிறகு', te: 'మిగతావి తర్వాత' },
  close:   { en: 'Close the list', hl: 'List band karo', hi: 'सूची बंद करो', pa: 'ਸੂਚੀ ਬੰਦ ਕਰੋ', gu: 'યાદી બંધ કરો',
             mr: 'यादी बंद करा', bn: 'তালিকা বন্ধ করুন', ta: 'பட்டியலை மூடு', te: 'జాబితా మూసేయండి' },
  keepNext:{ en: 'Keep for next time', hl: 'Agli baar ke liye rakh lo', hi: 'अगली बार के लिए रख लो', pa: 'ਅਗਲੀ ਵਾਰ ਲਈ ਰੱਖ ਲਓ',
             gu: 'આવતી વખત માટે રાખી લો', mr: 'पुढच्या वेळेसाठी ठेवा', bn: 'পরের বারের জন্য রেখে দিন',
             ta: 'அடுத்த முறைக்கு வைத்துக்கொள்', te: 'వచ్చేసారి కోసం ఉంచండి' },
  drop:    { en: 'Delete it', hl: 'Hata do', hi: 'हटा दो', pa: 'ਹਟਾ ਦਿਓ', gu: 'કાઢી નાખો', mr: 'काढून टाका', bn: 'সরিয়ে দিন',
             ta: 'நீக்கு', te: 'తీసేయండి' },
  closed:  { en: 'This list is closed.', hl: 'Yeh list band ho gayi.', hi: 'यह सूची बंद हो गई।', pa: 'ਇਹ ਸੂਚੀ ਬੰਦ ਹੋ ਗਈ।',
             gu: 'આ યાદી બંધ થઈ ગઈ.', mr: 'ही यादी बंद झाली.', bn: 'এই তালিকা বন্ধ হয়ে গেছে।', ta: 'இந்தப் பட்டியல் மூடப்பட்டது.',
             te: 'ఈ జాబితా మూసివేయబడింది.' },
  gone:    { en: 'This list is no longer here.', hl: 'Yeh list ab nahi hai.', hi: 'यह सूची अब नहीं है।', pa: 'ਇਹ ਸੂਚੀ ਹੁਣ ਨਹੀਂ ਹੈ।',
             gu: 'આ યાદી હવે નથી.', mr: 'ही यादी आता नाही.', bn: 'এই তালিকা আর নেই।', ta: 'இந்தப் பட்டியல் இப்போது இல்லை.',
             te: 'ఈ జాబితా ఇప్పుడు లేదు.' },
  where:   { en: '🛍️ Where to buy?', hl: '🛍️ Kahan milega?', hi: '🛍️ कहाँ मिलेगा?', pa: '🛍️ ਕਿੱਥੋਂ ਮਿਲੇਗਾ?', gu: '🛍️ ક્યાં મળશે?',
             mr: '🛍️ कुठे मिळेल?', bn: '🛍️ কোথায় পাব?', ta: '🛍️ எங்கே கிடைக்கும்?', te: '🛍️ ఎక్కడ దొరుకుతుంది?' },
}
