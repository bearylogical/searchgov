import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [sveltekit()],
	server: {
		// Proxy /api calls to the FastAPI server during development so the
		// frontend dev server and the API can run on different ports.
		proxy: {
			'/api': {
				target: 'http://localhost:8081',
				changeOrigin: true
			}
		}
	}
});
