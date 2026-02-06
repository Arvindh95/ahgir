import { CheckSquare, Download, Loader2 } from 'lucide-react'

interface SelectionToolbarProps {
  selectedCount: number
  totalCount: number
  onSelectAll: () => void
  onBulkDownload: () => void
  downloading: boolean
  allowDownloads: boolean
}

export default function SelectionToolbar({
  selectedCount,
  totalCount,
  onSelectAll,
  onBulkDownload,
  downloading,
  allowDownloads,
}: SelectionToolbarProps) {
  if (!allowDownloads) return null

  return (
    <div className="mb-6 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 glass-card p-4 rounded-xl">
      <div className="flex items-center gap-4">
        <button onClick={onSelectAll} className="flex items-center gap-2 text-sm text-gray-300 hover:text-white transition-colors">
          <CheckSquare className="w-4 h-4" />
          {selectedCount === totalCount ? 'Deselect All' : 'Select All'}
        </button>
        {selectedCount > 0 && (
          <span className="text-sm text-gray-400">{selectedCount} selected</span>
        )}
      </div>
      {selectedCount > 0 && (
        <button
          onClick={onBulkDownload}
          disabled={downloading}
          className="flex items-center gap-2 bg-white text-black px-5 py-2 rounded-lg font-bold hover:bg-gray-200 transition-colors disabled:opacity-50"
        >
          {downloading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
          Download {selectedCount} {selectedCount === 1 ? 'Photo' : 'Photos'}
        </button>
      )}
    </div>
  )
}
