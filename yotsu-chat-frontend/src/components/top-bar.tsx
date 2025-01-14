import { Search } from 'lucide-react'

export function TopBar() {
  return (
    <div className="h-[60px] border-b border-[#5a3c5a] flex items-center px-4">
      <div className="flex-1 relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-500" />
        <input
          type="text"
          placeholder="Search Yotsu Chat"
          className="w-full h-[42px] bg-white border border-gray-200 rounded-md pl-10 pr-4 text-sm text-gray-900 placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-gray-200"
        />
      </div>
    </div>
  )
}

