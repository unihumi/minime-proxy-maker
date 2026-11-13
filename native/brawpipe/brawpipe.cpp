// brawpipe - kleines Hilfsprogramm fuer Proxy Maker.
// Decodiert Blackmagic RAW (.braw) mit dem offiziellen Blackmagic RAW SDK.
//
//   brawpipe info  <libdir> <clip.braw> <scale>   Metadaten (key=value)
//   brawpipe video <libdir> <clip.braw> <scale>   RGB 16 Bit (rgb48le) nach stdout
//   brawpipe audio <libdir> <clip.braw> <out.wav> Tonspur als WAV
//
// <scale>: 1 = voll, 2 = halb, 4 = viertel, 8 = achtel
// Das Bild wird mit den Kamera-Metadaten des Clips entwickelt.

#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif

#include "BlackmagicRawAPI.h"

#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

#ifndef STDMETHODCALLTYPE
#define STDMETHODCALLTYPE
#endif

// ------------------------------------------------------- Plattform-Strings
#if defined(__APPLE__)
typedef CFStringRef BrawStr;
static BrawStr MakeStr(const char* utf8) {
    return CFStringCreateWithCString(nullptr, utf8, kCFStringEncodingUTF8);
}
static void FreeStr(BrawStr s) { if (s) CFRelease(s); }
static std::string ToUtf8(BrawStr s) {
    if (!s) return "";
    char buf[512] = {0};
    CFStringGetCString(s, buf, sizeof(buf), kCFStringEncodingUTF8);
    return buf;
}
#elif defined(_WIN32)
typedef BSTR BrawStr;
static BrawStr MakeStr(const char* utf8) {
    int n = MultiByteToWideChar(CP_UTF8, 0, utf8, -1, nullptr, 0);
    std::wstring w(n, L'\0');
    MultiByteToWideChar(CP_UTF8, 0, utf8, -1, &w[0], n);
    return SysAllocString(w.c_str());
}
static void FreeStr(BrawStr s) { if (s) SysFreeString(s); }
static std::string ToUtf8(BrawStr s) {
    if (!s) return "";
    int n = WideCharToMultiByte(CP_UTF8, 0, s, -1, nullptr, 0, nullptr, nullptr);
    std::string out(n > 0 ? n - 1 : 0, '\0');
    if (n > 1) WideCharToMultiByte(CP_UTF8, 0, s, -1, &out[0], n, nullptr, nullptr);
    return out;
}
#else  // Linux
typedef const char* BrawStr;
static BrawStr MakeStr(const char* utf8) { return strdup(utf8); }
static void FreeStr(BrawStr s) { free((void*)s); }
static std::string ToUtf8(BrawStr s) { return s ? s : ""; }
#endif

static int Fail(const char* msg, HRESULT hr = 0) {
    std::fprintf(stderr, "brawpipe: %s (0x%08x)\n", msg, (unsigned)hr);
    return 1;
}

static BlackmagicRawResolutionScale ScaleFromInt(int s) {
    switch (s) {
        case 2: return blackmagicRawResolutionScaleHalf;
        case 4: return blackmagicRawResolutionScaleQuarter;
        case 8: return blackmagicRawResolutionScaleEighth;
        default: return blackmagicRawResolutionScaleFull;
    }
}

// ------------------------------------------------------------- Callback
class Callback : public IBlackmagicRawCallback {
public:
    BlackmagicRawResolutionScale scale = blackmagicRawResolutionScaleFull;
    bool writeFrames = false;       // video: Pixel nach stdout
    std::atomic<bool> failed{false};
    uint32_t outW = 0, outH = 0;    // Groesse des entwickelten Bildes

    void ReadComplete(IBlackmagicRawJob* readJob, HRESULT result,
                      IBlackmagicRawFrame* frame) override {
        IBlackmagicRawJob* decodeJob = nullptr;
        if (result == S_OK) result = frame->SetResourceFormat(blackmagicRawResourceFormatRGBU16);
        if (result == S_OK) result = frame->SetResolutionScale(scale);
        if (result == S_OK) result = frame->CreateJobDecodeAndProcessFrame(nullptr, nullptr, &decodeJob);
        if (result == S_OK) result = decodeJob->Submit();
        if (result != S_OK) {
            failed = true;
            if (decodeJob) decodeJob->Release();
        }
        readJob->Release();
    }

    void ProcessComplete(IBlackmagicRawJob* job, HRESULT result,
                         IBlackmagicRawProcessedImage* image) override {
        if (result == S_OK) {
            uint32_t w = 0, h = 0, size = 0;
            void* data = nullptr;
            image->GetWidth(&w);
            image->GetHeight(&h);
            image->GetResourceSizeBytes(&size);
            image->GetResource(&data);
            outW = w;
            outH = h;
            if (writeFrames && data) {
                const size_t need = size_t(w) * h * 6;  // 3 Kanaele x 16 Bit
                const size_t n = need <= size ? need : size;
                if (std::fwrite(data, 1, n, stdout) != n) failed = true;
            }
        } else {
            failed = true;
        }
        job->Release();
    }

    void DecodeComplete(IBlackmagicRawJob*, HRESULT) override {}
    void ReadAudioComplete(IBlackmagicRawJob*, HRESULT, IBlackmagicRawAudioBuffer*) override {}
    void TrimProgress(IBlackmagicRawJob*, float) override {}
    void TrimComplete(IBlackmagicRawJob*, HRESULT) override {}
    void SidecarMetadataParseWarning(IBlackmagicRawClip*, BrawStr, uint32_t, BrawStr) override {}
    void SidecarMetadataParseError(IBlackmagicRawClip*, BrawStr, uint32_t, BrawStr) override {}
    void PreparePipelineComplete(void*, HRESULT) override {}

    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID, LPVOID*) override { return E_NOTIMPL; }
    ULONG STDMETHODCALLTYPE AddRef() override { return 0; }
    ULONG STDMETHODCALLTYPE Release() override { return 0; }
};

// --------------------------------------------------------------- Helfer
struct Session {
    IBlackmagicRawFactory* factory = nullptr;
    IBlackmagicRaw* codec = nullptr;
    IBlackmagicRawClip* clip = nullptr;
    ~Session() {
        if (clip) clip->Release();
        if (codec) codec->Release();
        if (factory) factory->Release();
    }
};

#if defined(_WIN32)
// Laedt die Factory ohne Installation/Registrierung:
// 1. exportierte Funktion CreateBlackmagicRawFactoryInstance (falls vorhanden)
// 2. Standard-COM-Weg ueber DllGetClassObject der DLL
// 3. registrierte COM-Komponente einer installierten Blackmagic-RAW-Version
static IBlackmagicRawFactory* LoadFactoryWin(const char* libdir) {
    int n = MultiByteToWideChar(CP_UTF8, 0, libdir, -1, nullptr, 0);
    std::wstring dir(n, L'\0');
    MultiByteToWideChar(CP_UTF8, 0, libdir, -1, &dir[0], n);
    dir.resize(wcslen(dir.c_str()));
    SetDllDirectoryW(dir.c_str());  // Decoder-DLLs liegen daneben
    const std::wstring dll = dir + L"\\BlackmagicRawAPI.dll";
    HMODULE mod = LoadLibraryExW(dll.c_str(), nullptr, LOAD_WITH_ALTERED_SEARCH_PATH);
    IBlackmagicRawFactory* factory = nullptr;
    if (mod) {
        typedef IBlackmagicRawFactory* (*CreateFn)();
        if (CreateFn create = (CreateFn)GetProcAddress(mod, "CreateBlackmagicRawFactoryInstance"))
            factory = create();
        if (!factory) {
            typedef HRESULT(STDAPICALLTYPE * GetClassFn)(REFCLSID, REFIID, LPVOID*);
            if (GetClassFn getClass = (GetClassFn)GetProcAddress(mod, "DllGetClassObject")) {
                IClassFactory* cf = nullptr;
                if (getClass(CLSID_CBlackmagicRawFactory, IID_IClassFactory, (LPVOID*)&cf) == S_OK && cf) {
                    cf->CreateInstance(nullptr, IID_IBlackmagicRawFactory, (LPVOID*)&factory);
                    cf->Release();
                }
            }
        }
    }
    if (!factory)
        CoCreateInstance(CLSID_CBlackmagicRawFactory, nullptr, CLSCTX_ALL,
                         IID_IBlackmagicRawFactory, (LPVOID*)&factory);
    return factory;
}
#endif

static int Open(Session& s, const char* libdir, const char* path, Callback* cb) {
#if defined(_WIN32)
    // Windows: BlackmagicRawAPI.dll aus dem mitgelieferten Ordner laden.
    s.factory = LoadFactoryWin(libdir);
#else
    BrawStr lib = MakeStr(libdir);
    s.factory = CreateBlackmagicRawFactoryInstanceFromPath(lib);
    FreeStr(lib);
#endif
    if (!s.factory) return Fail("Blackmagic RAW Bibliothek nicht gefunden");
    HRESULT hr = s.factory->CreateCodec(&s.codec);
    if (hr != S_OK) return Fail("CreateCodec", hr);
    BrawStr file = MakeStr(path);
    hr = s.codec->OpenClip(file, &s.clip);
    FreeStr(file);
    if (hr != S_OK) return Fail("Clip konnte nicht geoeffnet werden", hr);
    if (cb) {
        hr = s.codec->SetCallback(cb);
        if (hr != S_OK) return Fail("SetCallback", hr);
    }
    return 0;
}

static bool DecodeFrame(Session& s, uint64_t index) {
    IBlackmagicRawJob* job = nullptr;
    if (s.clip->CreateJobReadFrame(index, &job) != S_OK) return false;
    if (job->Submit() != S_OK) {
        job->Release();
        return false;
    }
    s.codec->FlushJobs();  // wartet, bis Lesen + Entwickeln fertig sind
    return true;
}

// ---------------------------------------------------------------- Modi
static int CmdInfo(const char* libdir, const char* path, int scale) {
    Callback cb;
    cb.scale = ScaleFromInt(scale);
    Session s;
    if (int r = Open(s, libdir, path, &cb)) return r;

    uint32_t w = 0, h = 0;
    float fps = 0;
    uint64_t frames = 0;
    s.clip->GetWidth(&w);
    s.clip->GetHeight(&h);
    s.clip->GetFrameRate(&fps);
    s.clip->GetFrameCount(&frames);
    std::printf("width=%u\nheight=%u\nfps=%.6f\nframes=%llu\n", w, h, fps,
                (unsigned long long)frames);

    BrawStr tc = nullptr;
    if (s.clip->GetTimecodeForFrame(0, &tc) == S_OK && tc) {
        std::printf("timecode=%s\n", ToUtf8(tc).c_str());
        FreeStr(tc);
    }

    IBlackmagicRawClipAudio* audio = nullptr;
    if (s.clip->QueryInterface(IID_IBlackmagicRawClipAudio, (LPVOID*)&audio) == S_OK && audio) {
        uint32_t ch = 0, rate = 0, bits = 0;
        uint64_t samples = 0;
        audio->GetAudioChannelCount(&ch);
        audio->GetAudioSampleRate(&rate);
        audio->GetAudioBitDepth(&bits);
        audio->GetAudioSampleCount(&samples);
        std::printf("audio_channels=%u\naudio_rate=%u\naudio_bits=%u\naudio_samples=%llu\n",
                    ch, rate, bits, (unsigned long long)samples);
        audio->Release();
    }

    // Tatsaechliche Groesse bei dieser Decode-Aufloesung ermitteln
    if (frames > 0 && DecodeFrame(s, 0) && !cb.failed)
        std::printf("scaled_width=%u\nscaled_height=%u\n", cb.outW, cb.outH);
    std::fflush(stdout);
    return 0;
}

static int CmdVideo(const char* libdir, const char* path, int scale) {
#ifdef _WIN32
    _setmode(_fileno(stdout), _O_BINARY);
#endif
    Callback cb;
    cb.scale = ScaleFromInt(scale);
    cb.writeFrames = true;
    Session s;
    if (int r = Open(s, libdir, path, &cb)) return r;
    uint64_t frames = 0;
    s.clip->GetFrameCount(&frames);
    for (uint64_t i = 0; i < frames; ++i) {
        if (!DecodeFrame(s, i) || cb.failed)
            return Fail("Frame konnte nicht decodiert werden");
    }
    std::fflush(stdout);
    return 0;
}

static void PutLE(std::FILE* f, uint32_t v, int bytes) {
    for (int i = 0; i < bytes; ++i) std::fputc((v >> (8 * i)) & 0xff, f);
}

static int CmdAudio(const char* libdir, const char* path, const char* wavPath) {
    Session s;
    if (int r = Open(s, libdir, path, nullptr)) return r;
    IBlackmagicRawClipAudio* audio = nullptr;
    if (s.clip->QueryInterface(IID_IBlackmagicRawClipAudio, (LPVOID*)&audio) != S_OK || !audio)
        return Fail("Clip hat keinen Ton");
    uint32_t ch = 0, rate = 0, bits = 0;
    uint64_t total = 0;
    audio->GetAudioChannelCount(&ch);
    audio->GetAudioSampleRate(&rate);
    audio->GetAudioBitDepth(&bits);
    audio->GetAudioSampleCount(&total);
    if (!ch || !rate || !bits || !total) {
        audio->Release();
        return Fail("Clip hat keinen Ton");
    }

#ifdef _WIN32
    int n = MultiByteToWideChar(CP_UTF8, 0, wavPath, -1, nullptr, 0);
    std::wstring wpath(n, L'\0');
    MultiByteToWideChar(CP_UTF8, 0, wavPath, -1, &wpath[0], n);
    std::FILE* f = _wfopen(wpath.c_str(), L"wb");
#else
    std::FILE* f = std::fopen(wavPath, "wb");
#endif
    if (!f) {
        audio->Release();
        return Fail("WAV-Datei kann nicht geschrieben werden");
    }
    const uint32_t frameBytes = ch * (bits / 8);
    std::fwrite("RIFF\0\0\0\0WAVEfmt ", 1, 16, f);
    PutLE(f, 16, 4);
    PutLE(f, 1, 2);  // PCM
    PutLE(f, ch, 2);
    PutLE(f, rate, 4);
    PutLE(f, rate * frameBytes, 4);
    PutLE(f, frameBytes, 2);
    PutLE(f, bits, 2);
    std::fwrite("data\0\0\0\0", 1, 8, f);

    const uint32_t chunk = 48000;
    std::vector<uint8_t> buf(size_t(chunk) * frameBytes);
    uint64_t pos = 0, dataBytes = 0;
    while (pos < total) {
        uint32_t samplesRead = 0, bytesRead = 0;
        HRESULT hr = audio->GetAudioSamples((int64_t)pos, buf.data(), (uint32_t)buf.size(),
                                            chunk, &samplesRead, &bytesRead);
        if (hr != S_OK || samplesRead == 0) break;
        std::fwrite(buf.data(), 1, bytesRead, f);
        dataBytes += bytesRead;
        pos += samplesRead;
    }
    audio->Release();

    std::fseek(f, 4, SEEK_SET);
    PutLE(f, (uint32_t)(36 + dataBytes), 4);
    std::fseek(f, 40, SEEK_SET);
    PutLE(f, (uint32_t)dataBytes, 4);
    std::fclose(f);
    return dataBytes ? 0 : Fail("Keine Audiodaten gelesen");
}

// ---------------------------------------------------------------- main
static int Run(int argc, char** argv) {
    if (argc < 5) {
        std::fprintf(stderr,
                     "usage: brawpipe info|video <libdir> <clip.braw> <scale>\n"
                     "       brawpipe audio <libdir> <clip.braw> <out.wav>\n");
        return 2;
    }
    const std::string mode = argv[1];
    if (mode == "info") return CmdInfo(argv[2], argv[3], std::atoi(argv[4]));
    if (mode == "video") return CmdVideo(argv[2], argv[3], std::atoi(argv[4]));
    if (mode == "audio") return CmdAudio(argv[2], argv[3], argv[4]);
    return Fail("unbekannter Modus");
}

#ifdef _WIN32
int wmain(int argc, wchar_t** wargv) {
    CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    std::vector<std::string> args;
    for (int i = 0; i < argc; ++i) {
        int n = WideCharToMultiByte(CP_UTF8, 0, wargv[i], -1, nullptr, 0, nullptr, nullptr);
        std::string a(n > 0 ? n - 1 : 0, '\0');
        if (n > 1) WideCharToMultiByte(CP_UTF8, 0, wargv[i], -1, &a[0], n, nullptr, nullptr);
        args.push_back(a);
    }
    std::vector<char*> argv;
    for (auto& a : args) argv.push_back(&a[0]);
    int r = Run(argc, argv.data());
    CoUninitialize();
    return r;
}
#else
int main(int argc, char** argv) { return Run(argc, argv); }
#endif
