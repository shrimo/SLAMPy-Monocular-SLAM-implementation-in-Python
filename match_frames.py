import cv2
import numpy as np
np.set_printoptions(suppress=True)

from skimage.measure import ransac
from skimage.transform import FundamentalMatrixTransform
from skimage.transform import EssentialMatrixTransform

#Getting rid of the outliers:
def extractRt(F):
    W = np.mat([[0,-1,0],[1,0,0],[0,0,1]],dtype=float)
    U, d, Vt = np.linalg.svd(F)
    #assert np.linalg.det(U) > 0
    if np.linalg.det(Vt) < 0:
        Vt *= -1.0
    # R = np.dot(np.dot(U, W), Vt)
    R = U @ W @ Vt
    if np.sum(R.diagonal()) < 0:
        # R = np.dot(np.dot(U, W.T), Vt)
        R = U @ W.T @ Vt
    t = U[:, 2]
    ret = np.eye(4)
    ret[:3, :3] = R
    ret[:3, 3] = t
    #print(d)
    return ret

def SLAMBFMatcher(des1, des2):
    bf = cv2.BFMatcher(cv2.NORM_HAMMING)
    return bf.knnMatch(des1.descriptors, des2.descriptors, k=2)

def SLAMFlannBasedMatcher(des1, des2):
    FLANN_INDEX_KDTREE = 1
    index_params = dict(algorithm = FLANN_INDEX_KDTREE, trees = 5)
    search_params = dict(checks = 50)
    flann = cv2.FlannBasedMatcher(index_params, search_params)
    return flann.knnMatch(des1.descriptors, des2.descriptors, k=2)

def generate_match(f1, f2):
    ''' Rewrite the Function into an Object (class) '''

    matches = SLAMBFMatcher(f1, f2)
    # bf = cv2.BFMatcher(cv2.NORM_HAMMING)
    # matches = bf.knnMatch(f1.descriptors, f2.descriptors, k=2)    
    
    ret = []
    x1, x2 = [], []

    for m,n in matches:
        if m.distance < 0.75*n.distance:
            pts1 = f1.key_pts[m.queryIdx]
            pts2 = f2.key_pts[m.trainIdx]

            # travel less than 10% of diagonal and be within orb distance 32
            if np.linalg.norm((pts1-pts2)) < 0.1*np.linalg.norm([f1.w, f1.h]) and m.distance < 32:
                # keep around indices
                # TODO: refactor this to not be O(N^2)
                if m.queryIdx not in x1 and m.trainIdx not in x2:
                    x1.append(m.queryIdx)
                    x2.append(m.trainIdx)
                    ret.append((pts1, pts2))

    # no duplicates
    assert(len(set(x1)) == len(x1))
    assert(len(set(x2)) == len(x2))
    
    assert len(ret) >= 8

    ret = np.array(ret)
    x1 = np.array(x1)
    x2 = np.array(x2)

    # RANdom SAmple Consensus
    model, f_pts = ransac((ret[:, 0], ret[:, 1]),
                    FundamentalMatrixTransform,
                    # EssentialMatrixTransform,
                    min_samples=8,
                    residual_threshold=0.001,
                    max_trials=100)

    # print("Matches: %d -> %d -> %d -> %d" % (len(f1.descriptors), len(matches), len(f_pts), sum(f_pts)))
    Rt = extractRt(model.params)    
    return x1[f_pts], x2[f_pts], Rt

