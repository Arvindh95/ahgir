import Link from 'next/link'
import { ChevronRight } from 'lucide-react'

interface Crumb {
  label: string
  href?: string
}

interface BreadcrumbsProps {
  crumbs: Crumb[]
}

export default function Breadcrumbs({ crumbs }: BreadcrumbsProps) {
  return (
    <nav className="flex items-center gap-1.5 text-sm mb-6">
      {crumbs.map((crumb, i) => {
        const isLast = i === crumbs.length - 1
        return (
          <span key={i} className="flex items-center gap-1.5">
            {i > 0 && <ChevronRight className="w-3.5 h-3.5 text-gray-600" />}
            {isLast || !crumb.href ? (
              <span className="text-white font-medium">{crumb.label}</span>
            ) : (
              <Link href={crumb.href} className="text-gray-400 hover:text-white transition-colors">
                {crumb.label}
              </Link>
            )}
          </span>
        )
      })}
    </nav>
  )
}
