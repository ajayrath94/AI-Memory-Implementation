// The choices behind the shortcuts above the text box.
//
// "Khabar" alone gave whatever the day's top story was; she might want
// Bengaluru's news, or the cricket, or nothing about politics at all. So a
// shortcut with kinds opens a sheet of big tiles, and each tile sends the
// sentence she would have said — Nancy answers it exactly as if typed, and
// the voice reads it out.
//
// Every label AND every sentence is in her language (all nine the app
// offers; i18n/words.ts). The sentence matters as much as the label: Nancy
// answers in the language she is asked in.

import { Words, pick as pickWords } from '../../i18n/words'

export type { Words }
export const pick = pickWords

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

export const SHEETS: Record<string, Sheet> = {
  news: {
    title: { en: 'Which news?', hl: 'Kaunsi khabar?', hi: 'कौनसी ख़बर?', pa: 'ਕਿਹੜੀ ਖ਼ਬਰ?', gu: 'કયા સમાચાર?',
             mr: 'कोणत्या बातम्या?', bn: 'কোন খবর?', ta: 'எந்த செய்தி?', te: 'ఏ వార్తలు?' },
    choices: [
      { id: 'local', emoji: '🏠',
        label: { en: 'Local', hl: 'Aas-paas', hi: 'आस-पास', pa: 'ਨੇੜੇ-ਤੇੜੇ', gu: 'આસપાસ', mr: 'जवळपास',
                 bn: 'স্থানীয়', ta: 'உள்ளூர்', te: 'స్థానిక' },
        say:   { en: "What's the news in my city today?", hl: 'Mere shehar ki aaj ki khabar sunao',
                 hi: 'मेरे शहर की आज की ख़बर सुनाओ', pa: 'ਮੇਰੇ ਸ਼ਹਿਰ ਦੀ ਅੱਜ ਦੀ ਖ਼ਬਰ ਸੁਣਾਓ',
                 gu: 'મારા શહેરના આજના સમાચાર સંભળાવો', mr: 'माझ्या शहरातल्या आजच्या बातम्या सांगा',
                 bn: 'আমার শহরের আজকের খবর শোনাও', ta: 'என் ஊரின் இன்றைய செய்திகளைச் சொல்லுங்கள்',
                 te: 'మా ఊరి ఈరోజు వార్తలు చెప్పండి' } },
      { id: 'india', emoji: '🇮🇳',
        label: { en: 'National', hl: 'Desh', hi: 'देश', pa: 'ਦੇਸ਼', gu: 'દેશ', mr: 'देश', bn: 'দেশ', ta: 'நாடு', te: 'దేశం' },
        say:   { en: "What's the news in India today?", hl: 'Desh ki aaj ki khabar sunao',
                 hi: 'देश की आज की ख़बर सुनाओ', pa: 'ਦੇਸ਼ ਦੀ ਅੱਜ ਦੀ ਖ਼ਬਰ ਸੁਣਾਓ', gu: 'દેશના આજના સમાચાર સંભળાવો',
                 mr: 'देशातल्या आजच्या बातम्या सांगा', bn: 'দেশের আজকের খবর শোনাও',
                 ta: 'நாட்டின் இன்றைய செய்திகளைச் சொல்லுங்கள்', te: 'దేశంలో ఈరోజు వార్తలు చెప్పండి' } },
      { id: 'entertainment', emoji: '🎬',
        label: { en: 'Entertainment', hl: 'Manoranjan', hi: 'मनोरंजन', pa: 'ਮਨੋਰੰਜਨ', gu: 'મનોરંજન', mr: 'मनोरंजन',
                 bn: 'বিনোদন', ta: 'பொழுதுபோக்கு', te: 'వినోదం' },
        say:   { en: "What's the news from films and TV today?", hl: 'Aaj filmon aur manoranjan ki khabar sunao',
                 hi: 'आज फ़िल्मों और मनोरंजन की ख़बर सुनाओ', pa: 'ਅੱਜ ਫ਼ਿਲਮਾਂ ਤੇ ਮਨੋਰੰਜਨ ਦੀ ਖ਼ਬਰ ਸੁਣਾਓ',
                 gu: 'આજના ફિલ્મ અને મનોરંજનના સમાચાર સંભળાવો', mr: 'आजच्या चित्रपट आणि मनोरंजनाच्या बातम्या सांगा',
                 bn: 'আজকের সিনেমা আর বিনোদনের খবর শোনাও', ta: 'இன்றைய சினிமா, பொழுதுபோக்குச் செய்திகளைச் சொல்லுங்கள்',
                 te: 'ఈరోజు సినిమా, వినోదం వార్తలు చెప్పండి' } },
      { id: 'sports', emoji: '🏏',
        label: { en: 'Sports', hl: 'Khel', hi: 'खेल', pa: 'ਖੇਡਾਂ', gu: 'રમતગમત', mr: 'खेळ', bn: 'খেলা', ta: 'விளையாட்டு', te: 'క్రీడలు' },
        say:   { en: "What's the sports news today?", hl: 'Aaj khel ki khabar sunao', hi: 'आज खेल की ख़बर सुनाओ',
                 pa: 'ਅੱਜ ਖੇਡਾਂ ਦੀ ਖ਼ਬਰ ਸੁਣਾਓ', gu: 'આજના રમતગમતના સમાચાર સંભળાવો', mr: 'आजच्या खेळाच्या बातम्या सांगा',
                 bn: 'আজকের খেলার খবর শোনাও', ta: 'இன்றைய விளையாட்டுச் செய்திகளைச் சொல்லுங்கள்',
                 te: 'ఈరోజు క్రీడా వార్తలు చెప్పండి' } },
      { id: 'all', emoji: '📰',
        label: { en: 'All', hl: 'Sab khabrein', hi: 'सब ख़बरें', pa: 'ਸਾਰੀਆਂ ਖ਼ਬਰਾਂ', gu: 'બધા સમાચાર', mr: 'सगळ्या बातम्या',
                 bn: 'সব খবর', ta: 'எல்லா செய்திகளும்', te: 'అన్ని వార్తలు' },
        say:   { en: "What are today's top stories?", hl: 'Aaj ki badi khabrein sunao', hi: 'आज की बड़ी ख़बरें सुनाओ',
                 pa: 'ਅੱਜ ਦੀਆਂ ਵੱਡੀਆਂ ਖ਼ਬਰਾਂ ਸੁਣਾਓ', gu: 'આજના મોટા સમાચાર સંભળાવો', mr: 'आजच्या मोठ्या बातम्या सांगा',
                 bn: 'আজকের বড় খবরগুলো শোনাও', ta: 'இன்றைய முக்கியச் செய்திகளைச் சொல்லுங்கள்',
                 te: 'ఈరోజు ముఖ్యమైన వార్తలు చెప్పండి' } },
    ],
  },

  lists: {
    title: { en: 'Your lists', hl: 'Aapki listein', hi: 'आपकी सूचियाँ', pa: 'ਤੁਹਾਡੀਆਂ ਸੂਚੀਆਂ', gu: 'તમારી યાદીઓ',
             mr: 'तुमच्या याद्या', bn: 'আপনার তালিকা', ta: 'உங்கள் பட்டியல்கள்', te: 'మీ జాబితాలు' },
    choices: [
      { id: 'see', emoji: '📋',
        label: { en: 'See my lists', hl: 'Listein dekho', hi: 'सूचियाँ देखो', pa: 'ਸੂਚੀਆਂ ਵੇਖੋ', gu: 'યાદીઓ જુઓ',
                 mr: 'याद्या पहा', bn: 'তালিকা দেখুন', ta: 'பட்டியல்களைப் பார்', te: 'జాబితాలు చూడండి' },
        open:  '/lists' },
      { id: 'read', emoji: '🔊',
        label: { en: 'Read my list', hl: 'List sunao', hi: 'सूची सुनाओ', pa: 'ਸੂਚੀ ਸੁਣਾਓ', gu: 'યાદી સંભળાવો',
                 mr: 'यादी वाचून दाखवा', bn: 'তালিকা শোনাও', ta: 'பட்டியலைப் படித்துக் காட்டு', te: 'జాబితా చదివి వినిపించండి' },
        say:   { en: 'Read my list out to me', hl: 'Meri list padhkar sunao', hi: 'मेरी सूची पढ़कर सुनाओ',
                 pa: 'ਮੇਰੀ ਸੂਚੀ ਪੜ੍ਹ ਕੇ ਸੁਣਾਓ', gu: 'મારી યાદી વાંચીને સંભળાવો', mr: 'माझी यादी वाचून दाखवा',
                 bn: 'আমার তালিকাটা পড়ে শোনাও', ta: 'என் பட்டியலைப் படித்துச் சொல்லுங்கள்',
                 te: 'నా జాబితా చదివి వినిపించండి' } },
      { id: 'shops', emoji: '🛍️',
        label: { en: 'Where to buy?', hl: 'Kahan milega?', hi: 'कहाँ मिलेगा?', pa: 'ਕਿੱਥੋਂ ਮਿਲੇਗਾ?', gu: 'ક્યાં મળશે?',
                 mr: 'कुठे मिळेल?', bn: 'কোথায় পাব?', ta: 'எங்கே கிடைக்கும்?', te: 'ఎక్కడ దొరుకుతుంది?' },
        // Her latest shopping list, with the shops already showing.
        open:  '/lists?shops=1' },
    ],
  },

  places: {
    title: { en: 'What are you looking for?', hl: 'Kya dhoondhna hai?', hi: 'क्या ढूँढना है?', pa: 'ਕੀ ਲੱਭਣਾ ਹੈ?',
             gu: 'શું શોધવું છે?', mr: 'काय शोधायचं आहे?', bn: 'কী খুঁজছেন?', ta: 'என்ன தேடுகிறீர்கள்?', te: 'ఏం వెతుకుతున్నారు?' },
    choices: [
      { id: 'temple', emoji: '🛕',
        label: { en: 'Temple', hl: 'Mandir', hi: 'मंदिर', pa: 'ਮੰਦਰ', gu: 'મંદિર', mr: 'मंदिर', bn: 'মন্দির', ta: 'கோயில்', te: 'గుడి' },
        say:   { en: 'Where is the nearest temple?', hl: 'Paas mein mandir kahan hai?', hi: 'पास में मंदिर कहाँ है?',
                 pa: 'ਨੇੜੇ ਮੰਦਰ ਕਿੱਥੇ ਹੈ?', gu: 'નજીકમાં મંદિર ક્યાં છે?', mr: 'जवळ मंदिर कुठे आहे?',
                 bn: 'কাছাকাছি মন্দির কোথায়?', ta: 'அருகில் கோயில் எங்கே இருக்கிறது?', te: 'దగ్గరలో గుడి ఎక్కడ ఉంది?' } },
      { id: 'park', emoji: '🌳',
        label: { en: 'Park', hl: 'Park', hi: 'पार्क', pa: 'ਪਾਰਕ', gu: 'બગીચો', mr: 'बाग', bn: 'পার্ক', ta: 'பூங்கா', te: 'పార్క్' },
        say:   { en: 'Where is a park nearby for a walk?', hl: 'Paas mein ghoomne ke liye park kahan hai?',
                 hi: 'पास में घूमने के लिए पार्क कहाँ है?', pa: 'ਨੇੜੇ ਸੈਰ ਲਈ ਪਾਰਕ ਕਿੱਥੇ ਹੈ?',
                 gu: 'નજીકમાં ફરવા માટે બગીચો ક્યાં છે?', mr: 'जवळ फिरायला बाग कुठे आहे?',
                 bn: 'কাছাকাছি হাঁটার জন্য পার্ক কোথায়?', ta: 'அருகில் நடக்கப் பூங்கா எங்கே இருக்கிறது?',
                 te: 'దగ్గరలో నడవడానికి పార్క్ ఎక్కడ ఉంది?' } },
      { id: 'pharmacy', emoji: '💊',
        label: { en: 'Pharmacy', hl: 'Dawai ki dukaan', hi: 'दवाई की दुकान', pa: 'ਦਵਾਈ ਦੀ ਦੁਕਾਨ', gu: 'દવાની દુકાન',
                 mr: 'औषधांचं दुकान', bn: 'ওষুধের দোকান', ta: 'மருந்துக் கடை', te: 'మందుల షాపు' },
        say:   { en: 'Where is the nearest pharmacy, and is it open now?', hl: 'Paas mein dawai ki dukaan kahan hai? Abhi khuli hai?',
                 hi: 'पास में दवाई की दुकान कहाँ है? अभी खुली है?', pa: 'ਨੇੜੇ ਦਵਾਈ ਦੀ ਦੁਕਾਨ ਕਿੱਥੇ ਹੈ? ਹੁਣ ਖੁੱਲ੍ਹੀ ਹੈ?',
                 gu: 'નજીકમાં દવાની દુકાન ક્યાં છે? અત્યારે ખુલ્લી છે?', mr: 'जवळ औषधांचं दुकान कुठे आहे? आत्ता उघडं आहे का?',
                 bn: 'কাছাকাছি ওষুধের দোকান কোথায়? এখন খোলা আছে?', ta: 'அருகில் மருந்துக் கடை எங்கே? இப்போது திறந்திருக்கிறதா?',
                 te: 'దగ్గరలో మందుల షాపు ఎక్కడ ఉంది? ఇప్పుడు తెరిచి ఉందా?' } },
      { id: 'doctor', emoji: '🩺',
        label: { en: 'Doctor / Hospital', hl: 'Doctor / Hospital', hi: 'डॉक्टर / अस्पताल', pa: 'ਡਾਕਟਰ / ਹਸਪਤਾਲ',
                 gu: 'ડૉક્ટર / હૉસ્પિટલ', mr: 'डॉक्टर / दवाखाना', bn: 'ডাক্তার / হাসপাতাল', ta: 'மருத்துவர் / மருத்துவமனை',
                 te: 'డాక్టర్ / ఆసుపత్రి' },
        say:   { en: 'Where is the nearest doctor or hospital?', hl: 'Paas mein doctor ya hospital kahan hai?',
                 hi: 'पास में डॉक्टर या अस्पताल कहाँ है?', pa: 'ਨੇੜੇ ਡਾਕਟਰ ਜਾਂ ਹਸਪਤਾਲ ਕਿੱਥੇ ਹੈ?',
                 gu: 'નજીકમાં ડૉક્ટર કે હૉસ્પિટલ ક્યાં છે?', mr: 'जवळ डॉक्टर किंवा दवाखाना कुठे आहे?',
                 bn: 'কাছাকাছি ডাক্তার বা হাসপাতাল কোথায়?', ta: 'அருகில் மருத்துவர் அல்லது மருத்துவமனை எங்கே?',
                 te: 'దగ్గరలో డాక్టర్ లేదా ఆసుపత్రి ఎక్కడ ఉంది?' } },
      { id: 'chai', emoji: '☕',
        label: { en: 'Tea & snacks', hl: 'Chai-nashta', hi: 'चाय-नाश्ता', pa: 'ਚਾਹ-ਨਾਸ਼ਤਾ', gu: 'ચા-નાસ્તો', mr: 'चहा-नाश्ता',
                 bn: 'চা-জলখাবার', ta: 'டீ, டிபன்', te: 'టీ, టిఫిన్' },
        say:   { en: 'Where is a good place nearby for tea and snacks?', hl: 'Paas mein chai-nashte ki achhi jagah kahan hai?',
                 hi: 'पास में चाय-नाश्ते की अच्छी जगह कहाँ है?', pa: 'ਨੇੜੇ ਚਾਹ-ਨਾਸ਼ਤੇ ਦੀ ਚੰਗੀ ਥਾਂ ਕਿੱਥੇ ਹੈ?',
                 gu: 'નજીકમાં ચા-નાસ્તાની સારી જગ્યા ક્યાં છે?', mr: 'जवळ चहा-नाश्त्यासाठी चांगली जागा कुठे आहे?',
                 bn: 'কাছাকাছি চা-জলখাবারের ভালো জায়গা কোথায়?', ta: 'அருகில் டீ, டிபனுக்கு நல்ல இடம் எங்கே?',
                 te: 'దగ్గరలో టీ, టిఫిన్‌కి మంచి చోటు ఎక్కడ ఉంది?' },
        now: h => (h >= 7 && h < 10) || (h >= 16 && h < 19) },
      { id: 'kirana', emoji: '🛒',
        label: { en: 'Groceries', hl: 'Kirana', hi: 'किराना', pa: 'ਕਰਿਆਨਾ', gu: 'કરિયાણું', mr: 'किराणा', bn: 'মুদির দোকান',
                 ta: 'மளிகைக் கடை', te: 'కిరాణా' },
        say:   { en: 'Where is the nearest grocery shop?', hl: 'Paas mein kirana ki dukaan kahan hai?',
                 hi: 'पास में किराने की दुकान कहाँ है?', pa: 'ਨੇੜੇ ਕਰਿਆਨੇ ਦੀ ਦੁਕਾਨ ਕਿੱਥੇ ਹੈ?',
                 gu: 'નજીકમાં કરિયાણાની દુકાન ક્યાં છે?', mr: 'जवळ किराणा दुकान कुठे आहे?',
                 bn: 'কাছাকাছি মুদির দোকান কোথায়?', ta: 'அருகில் மளிகைக் கடை எங்கே?', te: 'దగ్గరలో కిరాణా షాపు ఎక్కడ ఉంది?' } },
    ],
  },

  day: {
    title: { en: 'Your day', hl: 'Aapka din', hi: 'आपका दिन', pa: 'ਤੁਹਾਡਾ ਦਿਨ', gu: 'તમારો દિવસ', mr: 'तुमचा दिवस',
             bn: 'আপনার দিন', ta: 'உங்கள் நாள்', te: 'మీ రోజు' },
    choices: [
      { id: 'morning', emoji: '🌅',
        label: { en: 'Morning brief', hl: 'Subah ki baat', hi: 'सुबह की बात', pa: 'ਸਵੇਰ ਦੀ ਗੱਲ', gu: 'સવારની વાત',
                 mr: 'सकाळची गोष्ट', bn: 'সকালের কথা', ta: 'காலை விவரம்', te: 'ఉదయం కబుర్లు' },
        say:   { en: "Tell me about today — the weather, what I have on, and any festival.",
                 hl: 'Aaj ka haal batao — mausam, aaj ke kaam, aur koi tyohar ho to.',
                 hi: 'आज का हाल बताओ — मौसम, आज के काम, और कोई त्योहार हो तो।',
                 pa: 'ਅੱਜ ਦਾ ਹਾਲ ਦੱਸੋ — ਮੌਸਮ, ਅੱਜ ਦੇ ਕੰਮ, ਤੇ ਜੇ ਕੋਈ ਤਿਉਹਾਰ ਹੋਵੇ।',
                 gu: 'આજનો હાલ કહો — હવામાન, આજનાં કામ, અને કોઈ તહેવાર હોય તો.',
                 mr: 'आजचं सांगा — हवामान, आजची कामं, आणि कोणता सण असेल तर.',
                 bn: 'আজকের খবরাখবর বলো — আবহাওয়া, আজকের কাজ, আর কোনো উৎসব থাকলে।',
                 ta: 'இன்றைய நிலவரம் சொல்லுங்கள் — வானிலை, இன்றைய வேலைகள், ஏதாவது பண்டிகை இருந்தால் அதுவும்.',
                 te: 'ఈరోజు సంగతులు చెప్పండి — వాతావరణం, ఈరోజు పనులు, ఏదైనా పండుగ ఉంటే అది కూడా.' },
        now: h => h >= 5 && h < 11 },
      { id: 'today', emoji: '☀️',
        label: { en: 'Today', hl: 'Aaj', hi: 'आज', pa: 'ਅੱਜ', gu: 'આજે', mr: 'आज', bn: 'আজ', ta: 'இன்று', te: 'ఈరోజు' },
        say:   { en: "What's on my day today?", hl: 'Aaj mere din mein kya hai?', hi: 'आज मेरे दिन में क्या है?',
                 pa: 'ਅੱਜ ਮੇਰੇ ਦਿਨ ਵਿੱਚ ਕੀ ਹੈ?', gu: 'આજે મારા દિવસમાં શું છે?', mr: 'आज माझ्या दिवसात काय आहे?',
                 bn: 'আজ আমার দিনে কী আছে?', ta: 'இன்று என் நாளில் என்ன இருக்கிறது?', te: 'ఈరోజు నా రోజులో ఏముంది?' } },
      { id: 'tomorrow', emoji: '🌙',
        label: { en: 'Tomorrow', hl: 'Kal', hi: 'कल', pa: 'ਕੱਲ੍ਹ', gu: 'આવતીકાલ', mr: 'उद्या', bn: 'কাল', ta: 'நாளை', te: 'రేపు' },
        say:   { en: "What's on tomorrow?", hl: 'Kal mere din mein kya hai?', hi: 'कल मेरे दिन में क्या है?',
                 pa: 'ਕੱਲ੍ਹ ਮੇਰੇ ਦਿਨ ਵਿੱਚ ਕੀ ਹੈ?', gu: 'આવતીકાલે મારા દિવસમાં શું છે?', mr: 'उद्या माझ्या दिवसात काय आहे?',
                 bn: 'কাল আমার দিনে কী আছে?', ta: 'நாளை என் நாளில் என்ன இருக்கிறது?', te: 'రేపు నా రోజులో ఏముంది?' },
        now: h => h >= 19 },
      { id: 'week', emoji: '🗓️',
        label: { en: 'This week', hl: 'Is hafte', hi: 'इस हफ़्ते', pa: 'ਇਸ ਹਫ਼ਤੇ', gu: 'આ અઠવાડિયે', mr: 'या आठवड्यात',
                 bn: 'এই সপ্তাহে', ta: 'இந்த வாரம்', te: 'ఈ వారం' },
        say:   { en: 'What plans do I have this week?', hl: 'Is hafte mere kya kya plans hain?',
                 hi: 'इस हफ़्ते मेरे क्या-क्या प्लान हैं?', pa: 'ਇਸ ਹਫ਼ਤੇ ਮੇਰੇ ਕੀ ਕੀ ਪ੍ਰੋਗਰਾਮ ਹਨ?',
                 gu: 'આ અઠવાડિયે મારા શું શું કાર્યક્રમ છે?', mr: 'या आठवड्यात माझे काय काय कार्यक्रम आहेत?',
                 bn: 'এই সপ্তাহে আমার কী কী পরিকল্পনা আছে?', ta: 'இந்த வாரம் எனக்கு என்னென்ன திட்டங்கள் இருக்கின்றன?',
                 te: 'ఈ వారం నాకు ఏమేం పనులు ఉన్నాయి?' } },
      { id: 'add', emoji: '➕',
        label: { en: 'Add something', hl: 'Kuch jodo', hi: 'कुछ जोड़ो', pa: 'ਕੁਝ ਜੋੜੋ', gu: 'કંઈક ઉમેરો', mr: 'काहीतरी जोडा',
                 bn: 'কিছু যোগ করুন', ta: 'ஏதாவது சேர்', te: 'ఏదైనా జోడించండి' },
        open:  '/calendar?add=1' },
      { id: 'panchang', emoji: '🪔',
        label: { en: 'Panchang', hl: 'Panchang', hi: 'पंचांग', pa: 'ਪੰਚਾਂਗ', gu: 'પંચાંગ', mr: 'पंचांग', bn: 'পঞ্জিকা',
                 ta: 'பஞ்சாங்கம்', te: 'పంచాంగం' },
        say:   { en: "What is today's tithi? Is there a fast or festival today?",
                 hl: 'Aaj kaunsi tithi hai? Koi vrat ya tyohar hai?', hi: 'आज कौनसी तिथि है? कोई व्रत या त्योहार है?',
                 pa: 'ਅੱਜ ਕਿਹੜੀ ਤਿਥੀ ਹੈ? ਕੋਈ ਵਰਤ ਜਾਂ ਤਿਉਹਾਰ ਹੈ?', gu: 'આજે કઈ તિથિ છે? કોઈ વ્રત કે તહેવાર છે?',
                 mr: 'आज कोणती तिथी आहे? काही उपवास किंवा सण आहे का?', bn: 'আজ কোন তিথি? কোনো ব্রত বা উৎসব আছে?',
                 ta: 'இன்று என்ன திதி? ஏதாவது விரதம் அல்லது பண்டிகை இருக்கிறதா?',
                 te: 'ఈరోజు ఏ తిథి? ఏదైనా వ్రతం లేదా పండుగ ఉందా?' } },
    ],
  },
}
