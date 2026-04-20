// Version5/frontend/src/services/supabaseClient.js
import { createClient } from '@supabase/supabase-js';

// Get environment variables from Vite
const supabaseUrl = import.meta.env.VITE_SUPABASE_URL || 'https://cxewdzmqwjtnoptdvbrr.supabase.co';
const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY || 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImN4ZXdkem1xd2p0bm9wdGR2YnJyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ4MDU5MDEsImV4cCI6MjA5MDM4MTkwMX0.huCk0DwXvHxbMyWjadjGGVt6EfW-8c8h0h5ioEPhknY';

if (!supabaseUrl || !supabaseKey) {
  console.warn('Supabase URL or Key is missing. Ensure you have a .env file with VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY defined.');
}

export const supabase = createClient(supabaseUrl || 'https://placeholder-url.supabase.co', supabaseKey || 'placeholder-key');

// Helper function to insert a new podcast export
export async function insertPodcast(title, filePath, description) {
  try {
    const { data, error } = await supabase
      .from('podcasts')
      .insert([
        { title, file_path: filePath, description }
      ]);
    if (error) throw error;
    return data;
  } catch (error) {
    console.error('Error inserting podcast into Supabase:', error.message);
    throw error;
  }
}
