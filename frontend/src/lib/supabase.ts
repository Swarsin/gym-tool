import { createClient } from '@supabase/supabase-js'

const rawUrl = import.meta.env.VITE_SUPABASE_URL
const rawKey = import.meta.env.VITE_SUPABASE_ANON_KEY

if (!rawUrl || !rawKey) {
  console.warn(
    'Missing VITE_SUPABASE_URL or VITE_SUPABASE_ANON_KEY. Set these in your frontend environment variables.'
  )
}

export const supabaseUrl = (rawUrl || 'https://your-project.supabase.co')
  .replace(/['"]/g, '')
  .replace(/\/+$/, '')
  .trim()

export const supabaseAnonKey = (rawKey || 'your-anon-key')
  .replace(/['"]/g, '')
  .trim()

export const supabase = createClient(supabaseUrl, supabaseAnonKey)
