import fs from 'fs/promises';
import path from 'path';
import { createWorker } from 'tesseract.js';

const ROOT = '/workspace';
const BASENAME = 'GNM_2025-v010';

async function main() {
	const entries = await fs.readdir(ROOT, { withFileTypes: true });
	const dirs = entries
		.filter((d) => d.isDirectory() && d.name.startsWith(BASENAME + '_'))
		.map((d) => d.name)
		.sort();

	if (dirs.length === 0) {
		console.error('No page directories found');
		process.exit(1);
	}

	const worker = await createWorker('eng');

	for (const dir of dirs) {
		const pageDir = path.join(ROOT, dir);
		const imgPath = path.join(pageDir, 'page.png');
		try {
			const stat = await fs.stat(imgPath);
			if (!stat.isFile()) throw new Error('missing page.png');
			const result = await worker.recognize(imgPath);
			const text = result.data.text || '';
			await fs.writeFile(path.join(pageDir, 'ocr.txt'), text, 'utf8');
			console.log('OCR complete: ' + dir);
		} catch (err) {
			console.error('Skipping ' + dir + ': ' + (err && err.message ? err.message : String(err)));
		}
	}

	await worker.terminate();
}

main().catch((err) => {
	console.error('Fatal error:', err);
	process.exit(1);
});
