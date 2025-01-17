from multiprocessing import Process, Queue
import numpy as np
import OpenGL.GL as gl
import pangolin
# import g2o

def draw_axis(size):
    gl.glColor3f(1.0, 0.0, 0.0)
    pangolin.DrawLine([[0.0, 0.0, 0.0], [size, 0.0, 0.0]])
    gl.glColor3f(0.0, 1.0, 0.0)
    pangolin.DrawLine([[0.0, 0.0, 0.0], [0.0, -size, 0]])
    gl.glColor3f(0.0, 0.0, 1.0)
    pangolin.DrawLine([[0.0, 0.0, 0.0], [0.0, 0.0, size]])

def draw_grid(col):
    gl.glColor3f(0.7, 0.7, 0.7)
    for line in np.arange(col+1):
        pangolin.DrawLine([[line, 0.0, 0.0], [line, 0.0, col]])
        pangolin.DrawLine([[0.0, 0.0, line], [col, 0.0, line]])

def draw_keypoints(psize, points):
    gl.glPointSize(psize)
    gl.glColor3f(0.2, 0.6, 0.4)
    pangolin.DrawPoints(points)


class Point:
    # A Point is a 3-D point in the world
    # Each Point is observed in multiple Frames
    def __init__(self, mapp, loc):
        self.pt = loc
        self.frames = []
        self.idxs = []
        self.color = None
        self.id = len(mapp.points)
        mapp.points.append(self)

    def add_observation(self, frame, idx):
        frame.pts[idx] = self
        self.frames.append(frame)
        self.idxs.append(idx)

    def add_color(self, color):
        self.color = np.single(color) / 255.

class Descriptor:
    """Doc Descriptor"""
    def __init__(self, width = 1280, height = 720, psize = 2):
        self.width, self.height = width, height
        self.frames = []
        self.points = []
        self.state = None
        self.q3D = None # 3D data queue
        self.psize = psize
        self.tr = []
        self.mvla = (0, -20, -20, 0, 0, 0, 0, -1, 0)
        self.pmx = (width, height, 420, 420,
                    width//2, height//2, 0.2, 10000)

    # G2O optimization:
    def optimize(self):
        """ This method does not work, in development """
        err = optimize(self.frames, self.points, local_window, fix_points, verbose, rounds)
        # Key-Point Pruning:
        culled_pt_count = 0
        for p in self.points:
            # <= 4 match point that's old
            old_point = len(p.frames) <= 4 and p.frames[-1].id+7 < self.max_frame
            #handling the reprojection error
            errs = []
            for f,idx in zip(p.frames, p.idxs):
                uv = f.kps[idx]
                proj = np.dot(f.pose[:3], p.homogeneous())
                proj = proj[0:2] / proj[2]
                errs.append(np.linalg.norm(proj-uv))
            if old_point or np.mean(errs) > CULLING_ERR_THRES:
                culled_pt_count += 1
                self.points.remove(p)
                p.delete()

        return err

    def create_viewer(self):
        self.q3D = Queue()
        self.vp = Process(target=self.viewer_thread, args=(self.q3D,))
        self.vp.daemon = True
        self.vp.start()

    def release(self):
        # self.vp.kill()
        return self.vp.terminate()

    def viewer_thread(self, q3d):
        self.viewer_init()
        while True:
            self.viewer_refresh(q3d)

    def viewer_init(self):
        pangolin.CreateWindowAndBind('Viewport', self.width, self.height)
        gl.glEnable(gl.GL_DEPTH_TEST)

        self.scam = pangolin.OpenGlRenderState(
            pangolin.ProjectionMatrix(*self.pmx),
            pangolin.ModelViewLookAt(*self.mvla))
        self.handler = pangolin.Handler3D(self.scam)

        # Create Interactive View in window
        self.dcam = pangolin.CreateDisplay()
        self.dcam.SetBounds(0.0, 1.0, 0.0, 1.0, -self.width/self.height)
        self.dcam.SetHandler(self.handler)

        # Create panel
        self.panel = pangolin.CreatePanel('ui')
        self.panel.SetBounds(0.0, 0.2, 0.0, 100/640.)
        self.psize = pangolin.VarFloat('ui.Point_size', value=2, min=1, max=5)
        self.gain = pangolin.VarFloat('ui.Gain', value=1.0, min=0, max=3)
        self.background = pangolin.VarFloat('ui.Background', value=0.0, min=0, max=1)
        self.alpha = pangolin.VarFloat('ui.Alpha', value=1.0, min=0, max=1)
        self.screenshot = pangolin.VarBool('ui.Screenshot', value=False, toggle=False)

    def viewer_refresh(self, q3d):
        if self.state is None or not q3d.empty():
            self.state = q3d.get()

        gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)
        gl.glClearColor(self.background, self.background, self.background, self.alpha)
        self.dcam.Activate(self.scam)

        if pangolin.Pushed(self.screenshot):
            pangolin.SaveWindowOnRender('screenshot_'+str(len(self.state[1])))

        # draw Axis and Grid
        draw_axis(3.0)
        draw_grid(5.0)

        # draw keypoints
        gl.glPointSize(self.psize)
        # gl.glColor3f(self.R, self.G, self.B)
        # mul = np.array([self.R, self.G, self.B])
        pangolin.DrawPoints(self.state[1], self.state[4]*np.single(self.gain))

        # draw trajectory
        gl.glLineWidth(1)
        gl.glColor3f(0.1, 0.7, 1.0)
        pangolin.DrawLine(self.state[2])

        # draw all poses
        # gl.glColor3f(0.75, 0.75, 0.15)
        # pangolin.DrawCameras(self.state[0], 0.75, 0.75, 0.75)

        # draw current pose
        gl.glColor3f(1.0, 0.0, 0.0)
        pangolin.DrawCameras(self.state[3], 1.5, 0.75, 1.0)

        pangolin.FinishFrame()

    def put3D(self):
        ''' put 3D data in Queue '''
        if self.q3D is None:
            return
        poses, pts, cam_pts, color = [], [], [], []
        # get last element of list
        current_pose = [self.frames[-1].pose]
        for f in self.frames:
            x = f.pose.ravel()[3]
            y = f.pose.ravel()[7]
            z = f.pose.ravel()[11]
            cam_pts.append([x, y, z])
            poses.append(f.pose)
        for p in self.points:
            pts.append(p.pt)
            color.append(p.color)
        self.q3D.put((np.array(poses[:-1]), np.array(pts),
                    np.array(cam_pts), np.array(current_pose),
                    np.array(color)))

