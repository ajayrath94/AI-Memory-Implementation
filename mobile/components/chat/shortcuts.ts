// The choices behind the shortcuts above the text box.
//
// "Khabar" alone gave whatever the day's top story was; she might want
// Bengaluru's news, or the cricket, or nothing about politics at all. So a
// shortcut with kinds opens a sheet of big tiles, and each tile sends the
// sentence she would have said — Nancy answers it exactly as if typed, and
// the voice reads it out.
//
// Words are kept here per language (English, Hinglish, Hindi; the other
// languages fall back to English, as the rest of the app does) rather than in
// i18n/strings.ts, because each choice is a label and a sentence together.

export type Words = { en: string; hl: string; hi: string }

export type Choice = {
  id: string
  emoji: string
  label: Words
  say?: Words          // sent to Nancy
  open?: string        // a screen instead
  // Marked (not moved — she learns where each tile is) at the hours it is
  // most likely wanted.
  now?: (hour: number) => boolean
}

export type Sheet = { title: Words; choices: Choice[] }

export function pick(w: Words, lang: string): string {
  if (lang === 'hinglish') return w.hl
  if (lang === 'hindi') return w.hi
  return w.en
}

export const SHEETS: Record<string, Sheet> = {
  news: {
    title: { en: 'Which news?', hl: 'Kaunsi khabar?', hi: 'कौनसी ख़बर?' },
    choices: [
      { id: 'local', emoji: '🏠',
        label: { en: 'Local', hl: 'Aas-paas', hi: 'आस-पास' },
        say:   { en: "What's the news in my city today?",
                 hl: 'Mere shehar ki aaj ki khabar sunao',
                 hi: 'मेरे शहर की आज की ख़बर सुनाओ' } },
      { id: 'india', emoji: '🇮🇳',
        label: { en: 'National', hl: 'Desh', hi: 'देश' },
        say:   { en: "What's the news in India today?",
                 hl: 'Desh ki aaj ki khabar sunao',
                 hi: 'देश की आज की ख़बर सुनाओ' } },
      { id: 'entertainment', emoji: '🎬',
        label: { en: 'Entertainment', hl: 'Manoranjan', hi: 'मनोरंजन' },
        say:   { en: "What's the news from films and TV today?",
                 hl: 'Aaj filmon aur manoranjan ki khabar sunao',
                 hi: 'आज फ़िल्मों और मनोरंजन की ख़बर सुनाओ' } },
      { id: 'sports', emoji: '🏏',
        label: { en: 'Sports', hl: 'Khel', hi: 'खेल' },
        say:   { en: "What's the sports news today?",
                 hl: 'Aaj khel ki khabar sunao',
                 hi: 'आज खेल की ख़बर सुनाओ' } },
      { id: 'all', emoji: '📰',
        label: { en: 'All', hl: 'Sab khabrein', hi: 'सब ख़बरें' },
        say:   { en: "What are today's top stories?",
                 hl: 'Aaj ki badi khabrein sunao',
                 hi: 'आज की बड़ी ख़बरें सुनाओ' } },
    ],
  },

  lists: {
    title: { en: 'Your lists', hl: 'Aapki listein', hi: 'आपकी सूचियाँ' },
    choices: [
      { id: 'see', emoji: '📋',
        label: { en: 'See my lists', hl: 'Listein dekho', hi: 'सूचियाँ देखो' },
        open:  '/lists' },
      { id: 'read', emoji: '🔊',
        label: { en: 'Read my list', hl: 'List sunao', hi: 'सूची सुनाओ' },
        say:   { en: 'Read my list out to me',
                 hl: 'Meri list padhkar sunao',
                 hi: 'मेरी सूची पढ़कर सुनाओ' } },
      { id: 'shops', emoji: '🛍️',
        label: { en: 'Where to buy?', hl: 'Kahan milega?', hi: 'कहाँ मिलेगा?' },
        // Her latest shopping list, with the shops already showing.
        open:  '/lists?shops=1' },
    ],
  },

  places: {
    title: { en: 'What are you looking for?', hl: 'Kya dhoondhna hai?', hi: 'क्या ढूँढना है?' },
    choices: [
      { id: 'temple', emoji: '🛕',
        label: { en: 'Temple', hl: 'Mandir', hi: 'मंदिर' },
        say:   { en: 'Where is the nearest temple?',
                 hl: 'Paas mein mandir kahan hai?',
                 hi: 'पास में मंदिर कहाँ है?' } },
      { id: 'park', emoji: '🌳',
        label: { en: 'Park', hl: 'Park', hi: 'पार्क' },
        say:   { en: 'Where is a park nearby for a walk?',
                 hl: 'Paas mein ghoomne ke liye park kahan hai?',
                 hi: 'पास में घूमने के लिए पार्क कहाँ है?' } },
      { id: 'pharmacy', emoji: '💊',
        label: { en: 'Pharmacy', hl: 'Dawai ki dukaan', hi: 'दवाई की दुकान' },
        say:   { en: 'Where is the nearest pharmacy, and is it open now?',
                 hl: 'Paas mein dawai ki dukaan kahan hai? Abhi khuli hai?',
                 hi: 'पास में दवाई की दुकान कहाँ है? अभी खुली है?' } },
      { id: 'doctor', emoji: '🩺',
        label: { en: 'Doctor / Hospital', hl: 'Doctor / Hospital', hi: 'डॉक्टर / अस्पताल' },
        say:   { en: 'Where is the nearest doctor or hospital?',
                 hl: 'Paas mein doctor ya hospital kahan hai?',
                 hi: 'पास में डॉक्टर या अस्पताल कहाँ है?' } },
      { id: 'chai', emoji: '☕',
        label: { en: 'Tea & snacks', hl: 'Chai-nashta', hi: 'चाय-नाश्ता' },
        say:   { en: 'Where is a good place nearby for tea and snacks?',
                 hl: 'Paas mein chai-nashte ki achhi jagah kahan hai?',
                 hi: 'पास में चाय-नाश्ते की अच्छी जगह कहाँ है?' },
        now: h => (h >= 7 && h < 10) || (h >= 16 && h < 19) },
      { id: 'kirana', emoji: '🛒',
        label: { en: 'Groceries', hl: 'Kirana', hi: 'किराना' },
        say:   { en: 'Where is the nearest grocery shop?',
                 hl: 'Paas mein kirana ki dukaan kahan hai?',
                 hi: 'पास में किराने की दुकान कहाँ है?' } },
    ],
  },

  day: {
    title: { en: 'Your day', hl: 'Aapka din', hi: 'आपका दिन' },
    choices: [
      { id: 'morning', emoji: '🌅',
        label: { en: 'Morning brief', hl: 'Subah ki baat', hi: 'सुबह की बात' },
        say:   { en: "Tell me about today — the weather, what I have on, and any festival.",
                 hl: 'Aaj ka haal batao — mausam, aaj ke kaam, aur koi tyohar ho to.',
                 hi: 'आज का हाल बताओ — मौसम, आज के काम, और कोई त्योहार हो तो।' },
        now: h => h >= 5 && h < 11 },
      { id: 'today', emoji: '☀️',
        label: { en: 'Today', hl: 'Aaj', hi: 'आज' },
        say:   { en: "What's on my day today?",
                 hl: 'Aaj mere din mein kya hai?',
                 hi: 'आज मेरे दिन में क्या है?' } },
      { id: 'tomorrow', emoji: '🌙',
        label: { en: 'Tomorrow', hl: 'Kal', hi: 'कल' },
        say:   { en: "What's on tomorrow?",
                 hl: 'Kal mere din mein kya hai?',
                 hi: 'कल मेरे दिन में क्या है?' },
        now: h => h >= 19 },
      { id: 'week', emoji: '🗓️',
        label: { en: 'This week', hl: 'Is hafte', hi: 'इस हफ़्ते' },
        say:   { en: 'What plans do I have this week?',
                 hl: 'Is hafte mere kya kya plans hain?',
                 hi: 'इस हफ़्ते मेरे क्या-क्या प्लान हैं?' } },
      { id: 'add', emoji: '➕',
        label: { en: 'Add something', hl: 'Kuch jodo', hi: 'कुछ जोड़ो' },
        open:  '/calendar?add=1' },
      { id: 'panchang', emoji: '🪔',
        label: { en: 'Panchang', hl: 'Panchang', hi: 'पंचांग' },
        say:   { en: "What is today's tithi? Is there a fast or festival today?",
                 hl: 'Aaj kaunsi tithi hai? Koi vrat ya tyohar hai?',
                 hi: 'आज कौनसी तिथि है? कोई व्रत या त्योहार है?' } },
    ],
  },
}
