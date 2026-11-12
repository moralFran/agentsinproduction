package wsflate

import (
	"bytes"
	"compress/flate"
	"io"
	"testing"
)

func reviewWriter(buf *bytes.Buffer) *Writer {
	return NewWriter(buf, func(dst io.Writer) Compressor {
		w, err := flate.NewWriter(dst, 9)
		if err != nil { panic(err) }
		return w
	})
}

func reviewDecode(t *testing.T, buf *bytes.Buffer, want string) {
	t.Helper()
	data := append(append([]byte(nil), buf.Bytes()...), compressionReadTail[:]...)
	r := flate.NewReader(bytes.NewReader(data))
	defer r.Close()
	got, err := io.ReadAll(r)
	if err != nil || string(got) != want {
		t.Fatalf("wire=%x decoded=%q error=%v; want=%q without error", buf.Bytes(), got, err, want)
	}
}

func TestReviewCloseEmptyMessage(t *testing.T) {
	var buf bytes.Buffer
	w := reviewWriter(&buf)
	if err := w.Close(); err != nil { t.Fatal(err) }
	reviewDecode(t, &buf, "")
}

func TestReviewWriteAfterFlush(t *testing.T) {
	var buf bytes.Buffer
	w := reviewWriter(&buf)
	if _, err := w.Write([]byte("first")); err != nil { t.Fatal(err) }
	if err := w.Flush(); err != nil { t.Fatal(err) }
	if _, err := w.Write([]byte("second")); err != nil { t.Fatal(err) }
	if err := w.Close(); err != nil { t.Fatal(err) }
	reviewDecode(t, &buf, "firstsecond")
}

type reviewBadCompressor struct{}
func (*reviewBadCompressor) Write(p []byte) (int, error) { return len(p), nil }
func (*reviewBadCompressor) Flush() error { return nil }
func (*reviewBadCompressor) Close() error { return nil }

func TestReviewRejectBadEmptyCompressor(t *testing.T) {
	var buf bytes.Buffer
	w := NewWriter(&buf, func(io.Writer) Compressor { return &reviewBadCompressor{} })
	if err := w.Close(); err == nil { t.Fatal("Close accepted a compressor that never emits a sync-flush marker") }
}
