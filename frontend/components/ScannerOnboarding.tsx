import { useState, useEffect } from 'react'
import { Glasses, Sun, Focus, User, X } from 'lucide-react'

const STORAGE_KEY = 'scanner_onboarding_seen'

export default function ScannerOnboarding() {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    if (!localStorage.getItem(STORAGE_KEY)) {
      setVisible(true)
    }
  }, [])

  const dismiss = () => {
    localStorage.setItem(STORAGE_KEY, '1')
    setVisible(false)
  }

  if (!visible) return null

  const tips = [
    { icon: Glasses, text: 'Remove sunglasses and hats' },
    { icon: Sun, text: 'Ensure good, even lighting' },
    { icon: Focus, text: 'Face the camera directly' },
    { icon: User, text: 'Keep your face centered in the frame' },
  ]

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
      <div className="glass-card rounded-2xl p-8 max-w-md w-full relative border border-white/10">
        <button
          onClick={dismiss}
          className="absolute top-4 right-4 p-2 rounded-full hover:bg-white/10 text-gray-400 hover:text-white transition-colors"
        >
          <X className="w-5 h-5" />
        </button>

        <h2 className="text-2xl font-bold mb-2 text-center">Tips for Best Results</h2>
        <p className="text-gray-400 text-sm text-center mb-6">Follow these tips for accurate face matching</p>

        <div className="space-y-4 mb-8">
          {tips.map((tip, i) => (
            <div key={i} className="flex items-center gap-4 p-3 rounded-xl bg-white/5">
              <div className="w-10 h-10 rounded-full bg-blue-500/10 flex items-center justify-center flex-shrink-0">
                <tip.icon className="w-5 h-5 text-blue-400" />
              </div>
              <span className="text-gray-200 font-medium">{tip.text}</span>
            </div>
          ))}
        </div>

        <button
          onClick={dismiss}
          className="w-full py-3 bg-blue-600 text-white rounded-xl font-bold hover:bg-blue-700 transition-colors"
        >
          Got it
        </button>
      </div>
    </div>
  )
}
