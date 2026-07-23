export type Language = 'en' | 'hi';

export const translations = {
  en: {
    welcomeTitle: "Kynetic AI — Compute Marketplace",
    welcomeSubtitle: "Resource-agnostic compute rental connecting idle GPUs with AI developers.",
    hostOnboarding: "Monetize Your Hardware",
    hostStep1: "1. Install Host Agent",
    hostStep2: "2. Automatic Verification",
    hostStep3: "3. Publish & Earn",
    instanceManagement: "My Instances",
    copilotTitle: "AI Resource Copilot",
    copilotPlaceholder: "Ask Copilot e.g., 'I need an RTX 4090 to fine-tune Llama 3 8B under $1.50/hr'...",
    walletBalance: "Wallet Balance",
    topUp: "Top-Up Balance",
  },
  hi: {
    welcomeTitle: "काइनेटिक एआई — कंप्यूट मार्केटप्लेस",
    welcomeSubtitle: "निष्क्रिय जीपीयू को एआई डेवलपर्स से जोड़ने वाला कंप्यूट रेंटल प्लेटफॉर्म।",
    hostOnboarding: "अपने हार्डवेयर को मोनेटाइज करें",
    hostStep1: "1. होस्ट एजेंट इंस्टॉल करें",
    hostStep2: "2. स्वचालित सत्यापन",
    hostStep3: "3. प्रकाशित करें और कमाएं",
    instanceManagement: "मेरे इंस्टेंस",
    copilotTitle: "एआई रिसोर्स कोपायलट",
    copilotPlaceholder: "कोपायलट से पूछें उदा. 'मुझे $1.50/घंटे से कम में Llama 3 8B फ़ाइन-ट्यून करने के लिए RTX 4090 चाहिए'...",
    walletBalance: "वॉलेट बैलेंस",
    topUp: "बैलेंस टॉप-अप करें",
  },
};

export function getTranslation(lang: Language = 'en') {
  return translations[lang] || translations.en;
}
