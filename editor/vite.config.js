import { defineConfig } from 'vite';
export default defineConfig({build:{outDir:'../actions/analog-meter-reading/ui',emptyOutDir:true,sourcemap:false,lib:{entry:'src/editor.ts',formats:['es'],fileName:()=> 'editor.js'},minify:false}});
